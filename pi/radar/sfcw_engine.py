"""Stepped-Frequency Continuous Wave (SFCW) radar engine.

Orchestrates the bladeRF to sweep through discrete frequency steps,
capture IQ at each, and compute range profiles via IFFT.

Uses dual-channel reference: TX1+RX1 for antenna signal, TX2+RX2 as
phase reference (short cable loopback). Dividing signal by reference
eliminates random PLL phase offsets between TX and RX synthesizers.
"""

import json
import os
import threading
import time
import numpy as np

from bladerf_driver import BladeRFDriver
from bladerf._bladerf import ChannelLayout, Format, ffi, libbladeRF
import bladerf

LUT_PATH = os.path.join(os.path.dirname(__file__), 'tx1_amp_lut.json')
TX2_LUT_PATH = os.path.join(os.path.dirname(__file__), 'tx2_amp_lut.json')

SPEED_OF_LIGHT = 299_792_458


class SFCWEngine:
    def __init__(self, driver: BladeRFDriver):
        self.driver = driver
        self.start_freq = 2_000_000_000
        self.stop_freq = 5_000_000_000
        self.step_size = 20_000_000
        self.settle_time = 0.003
        self.num_buffers = 1
        self.tx1_gain = 30
        self.rx1_gain = 30
        self.tx2_gain = 30
        self.rx2_gain = 20
        self.rx_gain_min = 5
        self.rx_gain_max = 38
        self.range_offset = 0.5
        self.bscan_avg_count = 1
        self.bscan_primer = False
        self.running = False
        self._stop_event = threading.Event()
        self._thread = None
        self._callback = None
        self._lock = threading.Lock()
        self._background = None
        self._capture_background = False
        self._capture_bscan = False
        self._capture_bscan_bg = False
        self._bg_subtract_mode = 'complex'  # 'complex' or 'magnitude'
        self._last_h_cal = None
        self._fpga_tuning = False
        self._gains_dirty = False
        self._warm = False
        self._sweep_lock = threading.Lock()
        self._tx1_amp_lut = None
        self._tx1_amp_lut_freqs = None
        self._tx2_amp_lut = None
        self._tx2_amp_lut_freqs = None
        self._load_tx1_amp_lut()
        self._load_tx2_amp_lut()
        self._qt_profiles_rx = None
        self._qt_profiles_tx = None
        self._qt_params = None
        self._use_quick_tune = True
        self._rx_cond = threading.Condition()

    def _load_tx1_amp_lut(self):
        """Load per-frequency TX1 amplitude lookup table."""
        if not os.path.exists(LUT_PATH):
            print("[sfcw] No TX1 amplitude LUT found — using flat amplitude")
            return
        try:
            with open(LUT_PATH) as f:
                data = json.load(f)
            self._tx1_amp_lut_freqs = np.array(data['freq_hz'], dtype=np.float64)
            self._tx1_amp_lut = np.array(data['max_tx1_amplitude'], dtype=np.float64)
            print(f"[sfcw] TX1 amplitude LUT loaded: {len(self._tx1_amp_lut)} entries, "
                  f"range {self._tx1_amp_lut.min():.3f} - {self._tx1_amp_lut.max():.3f}")
        except Exception as e:
            print(f"[sfcw] Failed to load TX1 amplitude LUT: {e}")

    def _load_tx2_amp_lut(self):
        """Load per-frequency TX2 amplitude lookup table."""
        if not os.path.exists(TX2_LUT_PATH):
            print("[sfcw] No TX2 amplitude LUT found — using flat TX2 amplitude")
            return
        try:
            with open(TX2_LUT_PATH) as f:
                data = json.load(f)
            self._tx2_amp_lut_freqs = np.array(data['freq_hz'], dtype=np.float64)
            self._tx2_amp_lut = np.array(data['max_tx2_amplitude'], dtype=np.float64)
            print(f"[sfcw] TX2 amplitude LUT loaded: {len(self._tx2_amp_lut)} entries, "
                  f"range {self._tx2_amp_lut.min():.3f} - {self._tx2_amp_lut.max():.3f}")
        except Exception as e:
            print(f"[sfcw] Failed to load TX2 amplitude LUT: {e}")

    def _get_tx1_amplitude(self, freq_hz):
        """Interpolate the LUT to get max TX1 amplitude for a given frequency."""
        if self._tx1_amp_lut is None:
            return self.driver.tx_amplitude
        return float(np.interp(freq_hz, self._tx1_amp_lut_freqs, self._tx1_amp_lut))

    def _get_tx2_amplitude(self, freq_hz):
        """Interpolate the TX2 LUT to get max TX2 amplitude for a given frequency."""
        if self._tx2_amp_lut is None:
            return self._tx2_amp
        return float(np.interp(freq_hz, self._tx2_amp_lut_freqs, self._tx2_amp_lut))

    def _build_tx_dual_buffer(self, tx1_amp, tx2_amp):
        """Build an interleaved dual-channel TX buffer with separate amplitudes."""
        n_samples = int(self.driver.sample_rate * 0.01)
        t = np.arange(n_samples, dtype=np.float64) / self.driver.sample_rate
        phase = 2 * np.pi * self.driver.cw_offset * t
        SCALE = 2047

        tx1_i = np.clip(np.cos(phase) * tx1_amp * SCALE, -2048, 2047).astype(np.int16)
        tx1_q = np.clip(np.sin(phase) * tx1_amp * SCALE, -2048, 2047).astype(np.int16)
        tx2_i = np.clip(np.cos(phase) * tx2_amp * SCALE, -2048, 2047).astype(np.int16)
        tx2_q = np.clip(np.sin(phase) * tx2_amp * SCALE, -2048, 2047).astype(np.int16)

        buf = np.empty(n_samples * 4, dtype=np.int16)
        buf[0::4] = tx1_i
        buf[1::4] = tx1_q
        buf[2::4] = tx2_i
        buf[3::4] = tx2_q
        return buf.tobytes()

    @property
    def num_steps(self):
        return int((self.stop_freq - self.start_freq) / self.step_size) + 1

    @property
    def bandwidth(self):
        return self.stop_freq - self.start_freq

    @property
    def range_resolution(self):
        if self.bandwidth == 0:
            return float('inf')
        return SPEED_OF_LIGHT / (2 * self.bandwidth)

    @property
    def max_range(self):
        if self.step_size == 0:
            return float('inf')
        return SPEED_OF_LIGHT / (2 * self.step_size)

    def set_params(self, **kwargs):
        with self._lock:
            if 'start_freq' in kwargs:
                self.start_freq = int(kwargs['start_freq'])
            if 'stop_freq' in kwargs:
                self.stop_freq = int(kwargs['stop_freq'])
            if 'step_size' in kwargs:
                self.step_size = int(kwargs['step_size'])
            if 'settle_time' in kwargs:
                self.settle_time = float(kwargs['settle_time'])
            if 'num_buffers' in kwargs:
                self.num_buffers = max(1, int(kwargs['num_buffers']))
            if 'tx1_gain' in kwargs:
                self.tx1_gain = int(kwargs['tx1_gain'])
                self._gains_dirty = True
            if 'rx1_gain' in kwargs:
                self.rx1_gain = int(kwargs['rx1_gain'])
                self._gains_dirty = True
            if 'tx2_gain' in kwargs:
                self.tx2_gain = int(kwargs['tx2_gain'])
                self._gains_dirty = True
            if 'rx2_gain' in kwargs:
                self.rx2_gain = int(kwargs['rx2_gain'])
                self._gains_dirty = True
            if 'rx_gain_min' in kwargs:
                self.rx_gain_min = int(kwargs['rx_gain_min'])
            if 'rx_gain_max' in kwargs:
                self.rx_gain_max = int(kwargs['rx_gain_max'])
            if 'range_offset' in kwargs:
                self.range_offset = float(kwargs['range_offset'])
            if 'bscan_avg_count' in kwargs:
                self.bscan_avg_count = max(1, int(kwargs['bscan_avg_count']))
            if 'bscan_primer' in kwargs:
                self.bscan_primer = bool(kwargs['bscan_primer'])

    def get_params(self):
        return {
            'start_freq': self.start_freq,
            'stop_freq': self.stop_freq,
            'step_size': self.step_size,
            'settle_time': self.settle_time,
            'num_buffers': self.num_buffers,
            'tx1_gain': self.tx1_gain,
            'rx1_gain': self.rx1_gain,
            'tx2_gain': self.tx2_gain,
            'rx2_gain': self.rx2_gain,
            'rx_gain_min': self.rx_gain_min,
            'rx_gain_max': self.rx_gain_max,
            'range_offset': self.range_offset,
            'num_steps': self.num_steps,
            'bandwidth': self.bandwidth,
            'range_resolution': self.range_resolution,
            'max_range': self.max_range,
            'bscan_avg_count': self.bscan_avg_count,
            'bscan_primer': self.bscan_primer,
            'background_active': self._background is not None,
            'bg_subtract_mode': self._bg_subtract_mode,
        }

    def capture_background(self):
        self._capture_background = True

    def capture_bscan(self):
        self._capture_bscan = True

    def capture_bscan_bg(self):
        self._capture_bscan_bg = True

    def clear_background(self):
        self._background = None
        self._capture_background = False

    def set_bg_subtract_mode(self, mode):
        if mode in ('complex', 'magnitude'):
            self._bg_subtract_mode = mode
            if self._last_h_cal is not None and self._background is not None:
                result = self._process_h_cal(self._last_h_cal.copy())
                if self._callback and result:
                    self._callback(result)

    def run_coherence_test(self, callback=None):
        """Run 3 consecutive sweeps and compute repeatability + correlation metrics.

        Runs in a new thread. Results sent via callback as a dict with type='coherence_result'.
        """
        if self.running:
            return
        self.running = True
        self._stop_event.clear()
        t = threading.Thread(target=self._coherence_test_worker, args=(callback,), daemon=True)
        t.start()

    def _coherence_test_worker(self, callback):
        try:
            self._configure_hardware()
            self._start_tx_rx()
            time.sleep(0.1)

            sweeps = []
            for i in range(3):
                if self._stop_event.is_set():
                    return
                if callback:
                    callback({'type': 'progress', 'step': i, 'total': 3, 'freq_mhz': 0})
                result = self._perform_sweep()
                if result and result.get('type') == 'range_profile':
                    h_cal = np.array(result['h_cal_real']) + 1j * np.array(result['h_cal_imag'])
                    sweeps.append(h_cal)

            if len(sweeps) < 2:
                if callback:
                    callback({'error': 'Not enough sweeps completed'})
                return

            reps = []
            corrs = []
            for i in range(len(sweeps) - 1):
                a_raw = sweeps[i]
                b_raw = sweeps[i + 1]
                residual = b_raw - a_raw
                rep = 1.0 - (np.std(residual) / np.std(a_raw))
                reps.append(float(rep))
                a = a_raw - np.mean(a_raw)
                b = b_raw - np.mean(b_raw)
                corr = np.abs(np.sum(a * np.conj(b))) / (
                    np.sqrt(np.sum(np.abs(a) ** 2)) * np.sqrt(np.sum(np.abs(b) ** 2))
                )
                corrs.append(float(corr))

            if callback:
                callback({
                    'type': 'coherence_result',
                    'repeatability': reps,
                    'correlation': corrs,
                    'avg_repeatability': float(np.mean(reps)),
                    'avg_correlation': float(np.mean(corrs)),
                    'num_sweeps': len(sweeps),
                })
        except Exception as e:
            if callback:
                callback({'error': str(e)})
        finally:
            self._stop_tx_rx()
            self.running = False

    def run_single(self, callback):
        """Run a single sweep and stop. Used for B-scan position captures."""
        if self._warm:
            self._callback = callback
            t = threading.Thread(target=self._warm_sweep_worker, args=(callback,), daemon=True)
            t.start()
            return
        if self.running:
            return
        self._callback = callback
        self._stop_event.clear()
        self.running = True
        self._thread = threading.Thread(target=self._single_sweep_worker, daemon=True)
        self._thread.start()

    def _warm_sweep_worker(self, callback):
        """Perform averaged sweeps with hardware already running (warm B-scan mode)."""
        with self._sweep_lock:
            try:
                if self.bscan_primer:
                    self._perform_sweep_raw()

                avg_count = self.bscan_avg_count
                if avg_count <= 1:
                    result = self._perform_sweep()
                else:
                    h_cal_accum = None
                    completed = 0
                    for i in range(avg_count):
                        raw = self._perform_sweep_raw()
                        if raw is None:
                            continue
                        if h_cal_accum is None:
                            h_cal_accum = raw.copy()
                        else:
                            h_cal_accum += raw
                        completed += 1
                    if completed == 0:
                        result = None
                    else:
                        h_cal_avg = h_cal_accum / completed
                        self._last_h_cal = h_cal_avg.copy()
                        result = self._process_h_cal(h_cal_avg)
                if result is not None and callback:
                    callback(result)
            except Exception as e:
                print(f"[sfcw] Warm sweep error: {e}")
                if callback:
                    callback({'error': str(e)})

    def _single_sweep_worker(self):
        try:
            self._configure_hardware()
            self._start_tx_rx()
            time.sleep(0.1)
            result = self._perform_sweep()
            if result is not None and self._callback:
                self._callback(result)
        except Exception as e:
            print(f"[sfcw] Single sweep error: {e}")
            if self._callback:
                self._callback({'error': str(e)})
        finally:
            self._stop_tx_rx()
            self.running = False

    def warm_up(self):
        """Start hardware and keep it running for multiple on-demand sweeps (B-scan mode)."""
        if self._warm or self.running:
            return
        self._stop_event.clear()
        self._background = None
        self._capture_background = False
        self._configure_hardware()
        self._start_tx_rx()
        time.sleep(0.1)
        self._perform_sweep_raw()
        self._warm = True
        self.running = True

    def cool_down(self):
        """Stop hardware after warm B-scan session."""
        if not self._warm:
            return
        self._stop_tx_rx()
        self._warm = False
        self.running = False

    def start(self, callback):
        if self.running:
            return
        self._callback = callback
        self._stop_event.clear()
        self.running = True
        self._thread = threading.Thread(target=self._sweep_loop, daemon=True)
        self._thread.start()

    def stop(self):
        if not self.running:
            return
        if self._warm:
            self.cool_down()
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self.running = False

    def _sweep_loop(self):
        try:
            self._configure_hardware()
            self._start_tx_rx()

            while not self._stop_event.is_set():
                if not self.driver.tx_running or not self.driver.rx_running:
                    print("[sfcw] ERROR: TX/RX stream died unexpectedly")
                    if self._callback:
                        self._callback({'error': 'USB stream died — restart sweep'})
                    break
                if self._gains_dirty:
                    self._apply_gains()
                range_profile = self._perform_sweep()
                if range_profile is not None and self._callback:
                    self._callback(range_profile)

        except Exception as e:
            print(f"[sfcw] Sweep error: {e}")
            if self._callback:
                self._callback({'error': str(e)})
        finally:
            self._stop_tx_rx()
            self.running = False

    def _generate_quick_tune_profiles(self):
        """Generate and cache quick_tune profiles for all sweep frequencies.

        Must be called before streaming starts (set_frequency does full VCO cal).
        Profiles are reused across sweeps until parameters change.
        """
        with self._lock:
            start = self.start_freq
            stop = self.stop_freq
            step = self.step_size

        params_key = (start, stop, step)
        if self._qt_params == params_key and self._qt_profiles_rx is not None:
            print(f"[TIMING] Quick_tune profiles already cached (reusing)")
            return

        t_start = time.perf_counter()
        print(f"[TIMING] Generating quick_tune profiles...")

        num_steps = int((stop - start) / step) + 1
        freqs = np.linspace(start, stop, num_steps).astype(np.int64)
        dev_ptr = self.driver.device.dev[0]

        qt_rx = []
        qt_tx = []
        for i, f in enumerate(freqs):
            t0 = time.perf_counter()
            f_int = int(f)
            libbladeRF.bladerf_set_frequency(dev_ptr, bladerf.CHANNEL_RX(0), f_int)
            libbladeRF.bladerf_set_frequency(dev_ptr, bladerf.CHANNEL_TX(0), f_int)
            qr = ffi.new('struct bladerf_quick_tune *')
            qt_val = ffi.new('struct bladerf_quick_tune *')
            libbladeRF.bladerf_get_quick_tune(dev_ptr, bladerf.CHANNEL_RX(0), qr)
            libbladeRF.bladerf_get_quick_tune(dev_ptr, bladerf.CHANNEL_TX(0), qt_val)
            qt_rx.append(qr)
            qt_tx.append(qt_val)

            if i < 3 or i >= num_steps - 2:
                t_step = time.perf_counter() - t0
                print(f"  Profile {i}/{num_steps-1} @ {f_int/1e6:.0f} MHz: {t_step*1e6:7.1f} µs")

        self._qt_profiles_rx = qt_rx
        self._qt_profiles_tx = qt_tx
        self._qt_params = params_key

        t_total = time.perf_counter() - t_start
        print(f"[TIMING] Generated {num_steps} quick_tune profiles in {t_total*1e6:10.1f} µs ({t_total*1000:6.2f} ms)")

    def _configure_hardware(self):
        t_start = time.perf_counter()
        print(f"\n[TIMING] Configuring hardware...")

        t0 = time.perf_counter()
        self.driver.tx_gain = self.tx1_gain
        self.driver.rx_gain = self.rx1_gain
        self.driver.tx2_gain = self.tx2_gain
        self.driver.rx2_gain = self.rx2_gain
        self.driver.sample_rate = 10_000_000
        self.driver.bandwidth = 8_000_000
        self.driver.set_waveform('cw', offset=100_000, amplitude=0.9)
        t_basic_config = time.perf_counter() - t0

        if self._use_quick_tune:
            self._generate_quick_tune_profiles()

        t0 = time.perf_counter()
        self.driver._configure_channels_dual()
        t_channels = time.perf_counter() - t0

        t0 = time.perf_counter()
        self.driver.set_tuning_mode_fpga()
        t_tuning_mode = time.perf_counter() - t0
        self._fpga_tuning = True

        t_total = time.perf_counter() - t_start
        print(f"[TIMING] Hardware config: {t_basic_config*1e6:7.1f} µs (basic)")
        print(f"[TIMING] Channel config:  {t_channels*1e6:7.1f} µs (dual-channel)")
        print(f"[TIMING] Tuning mode:     {t_tuning_mode*1e6:7.1f} µs (FPGA)")
        print(f"[TIMING] Config total:    {t_total*1e6:7.1f} µs ({t_total*1000:.2f} ms)\n")

    def _start_tx_rx(self):
        t_start = time.perf_counter()
        print(f"[TIMING] Starting TX/RX streams...")

        t0 = time.perf_counter()
        self._rx_cond = threading.Condition()
        self._rx_latest = None
        self._rx_seq = 0
        n = 4096
        t = np.arange(n, dtype=np.float64) / self.driver.sample_rate
        self._ref_tone = np.exp(-1j * 2 * np.pi * self.driver.cw_offset * t)
        self._ref_tone_scaled = self._ref_tone / 2047.0
        t_prep = time.perf_counter() - t0

        t0 = time.perf_counter()
        self.driver.start_tx_dual()
        t_start_tx = time.perf_counter() - t0

        t0 = time.perf_counter()
        self.driver.start_rx_dual(self._rx_capture, num_samples=n)
        t_start_rx = time.perf_counter() - t0

        t0 = time.perf_counter()
        time.sleep(0.05)
        t_settle = time.perf_counter() - t0

        # Apply gains AFTER modules are enabled (enable_module resets gain state)
        t0 = time.perf_counter()
        dev_ptr = self.driver.device.dev[0]
        libbladeRF.bladerf_set_gain_mode(dev_ptr, bladerf.CHANNEL_RX(0), libbladeRF.BLADERF_GAIN_MGC)
        libbladeRF.bladerf_set_gain_mode(dev_ptr, bladerf.CHANNEL_RX(1), libbladeRF.BLADERF_GAIN_MGC)
        libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_RX(0), int(self.rx1_gain))
        libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_RX(1), int(self.rx2_gain))
        libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_TX(0), int(self.tx1_gain))
        libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_TX(1), int(self.tx2_gain))
        t_gains = time.perf_counter() - t0

        t_total = time.perf_counter() - t_start
        print(f"[TIMING] Ref tone prep:  {t_prep*1e6:8.1f} µs")
        print(f"[TIMING] Start TX:       {t_start_tx*1e6:8.1f} µs")
        print(f"[TIMING] Start RX:       {t_start_rx*1e6:8.1f} µs")
        print(f"[TIMING] Stream settle:  {t_settle*1e6:8.1f} µs (50ms sleep)")
        print(f"[TIMING] Apply gains:    {t_gains*1e6:8.1f} µs")
        print(f"[TIMING] Start total:    {t_total*1e6:8.1f} µs ({t_total*1000:.2f} ms)\n")

    def _apply_gains(self):
        dev_ptr = self.driver.device.dev[0]
        libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_TX(0), int(self.tx1_gain))
        libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_TX(1), int(self.tx2_gain))
        libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_RX(0), int(self.rx1_gain))
        libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_RX(1), int(self.rx2_gain))
        self._gains_dirty = False

    def _stop_tx_rx(self):
        self.driver.stop_rx_dual()
        self.driver.stop_tx_dual()
        # Restore single-channel config so calib panel works after SFCW
        self.driver._configure_channels()



    def _rx_capture(self, rx1_iq, rx2_iq):
        with self._rx_cond:
            self._rx_latest = (rx1_iq, rx2_iq)
            self._rx_seq += 1
            self._rx_cond.notify_all()

    def _perform_sweep(self):
        t_sweep_start = time.perf_counter()

        with self._lock:
            start = self.start_freq
            stop = self.stop_freq
            step = self.step_size
            settle = self.settle_time
            num_buffers = self.num_buffers

        num_steps = int((stop - start) / step) + 1
        freqs = np.linspace(start, stop, num_steps).astype(np.int64)
        h_signal = np.zeros(num_steps, dtype=np.complex128)
        h_reference = np.zeros(num_steps, dtype=np.complex128)

        dev_ptr = self.driver.device.dev[0]
        tx_ch = bladerf.CHANNEL_TX(0)
        rx_ch = bladerf.CHANNEL_RX(0)
        rx_ch1 = bladerf.CHANNEL_RX(1)

        use_qt = (self._use_quick_tune and self._qt_profiles_rx is not None
                  and len(self._qt_profiles_rx) == num_steps)
        settle_count = 10 if use_qt else 2

        dropped_steps = 0

        # Timing instrumentation
        enable_timing = True
        timing_steps = set(range(5)) | {num_steps - 2, num_steps - 1}
        all_step_times = []
        all_retune_times = []
        all_settle_times = []
        all_capture_times = []
        all_process_times = []

        for i in range(num_steps):
            t_step_start = time.perf_counter()
            do_log = enable_timing and i in timing_steps

            if self._stop_event.is_set():
                return None

            # === TIMING: Frequency retune ===
            t0 = time.perf_counter()
            f = int(freqs[i])
            if use_qt:
                libbladeRF.bladerf_schedule_retune(dev_ptr, rx_ch, 0, f, self._qt_profiles_rx[i])
                libbladeRF.bladerf_schedule_retune(dev_ptr, tx_ch, 0, f, self._qt_profiles_tx[i])
            else:
                libbladeRF.bladerf_set_frequency(dev_ptr, tx_ch, f)
                libbladeRF.bladerf_set_frequency(dev_ptr, rx_ch, f)
            t_retune = time.perf_counter() - t0

            # === TIMING: Wait for PLL settle ===
            t0 = time.perf_counter()
            with self._rx_cond:
                target_seq = self._rx_seq + settle_count
                while self._rx_seq < target_seq:
                    if not self._rx_cond.wait(timeout=1.0):
                        break
            t_settle = time.perf_counter() - t0

            # === TIMING: Capture buffers ===
            t0 = time.perf_counter()
            rx1_bufs = []
            rx2_bufs = []
            with self._rx_cond:
                last_seq = self._rx_seq

            for _ in range(num_buffers):
                with self._rx_cond:
                    while self._rx_seq <= last_seq:
                        if not self._rx_cond.wait(timeout=1.0):
                            break
                    if self._rx_seq > last_seq:
                        rx1_bufs.append(self._rx_latest[0])
                        rx2_bufs.append(self._rx_latest[1])
                        last_seq = self._rx_seq
            t_capture = time.perf_counter() - t0

            # === TIMING: Process buffers ===
            t0 = time.perf_counter()
            captured = len(rx1_bufs)
            if captured > 0:
                # Batch deinterleave + complex conversion + ref_tone correlation
                sig_arr = np.array(rx1_bufs, dtype=np.float64)
                ref_arr = np.array(rx2_bufs, dtype=np.float64)
                sig_cplx = (sig_arr[:, 0::2] + 1j * sig_arr[:, 1::2]) * self._ref_tone_scaled
                ref_cplx = (ref_arr[:, 0::2] + 1j * ref_arr[:, 1::2]) * self._ref_tone_scaled
                h_signal[i] = sig_cplx.mean()
                h_reference[i] = ref_cplx.mean()
            else:
                dropped_steps += 1
            t_process = time.perf_counter() - t0

            # === TIMING: Record and log ===
            t_step_total = time.perf_counter() - t_step_start
            all_step_times.append(t_step_total * 1e6)  # microseconds
            all_retune_times.append(t_retune * 1e6)
            all_settle_times.append(t_settle * 1e6)
            all_capture_times.append(t_capture * 1e6)
            all_process_times.append(t_process * 1e6)

            if do_log:
                print(f"\n[TIMING] Step {i}/{num_steps-1} @ {f/1e6:.0f} MHz:")
                print(f"  Retune:     {t_retune*1e6:8.1f} µs  ({'quick_tune' if use_qt else 'set_freq'})")
                print(f"  Settle:     {t_settle*1e6:8.1f} µs  (wait for {settle_count} buffers)")
                print(f"  Capture:    {t_capture*1e6:8.1f} µs  ({captured} buffers)")
                print(f"  Process:    {t_process*1e6:8.1f} µs  (demod + correlation)")
                print(f"  STEP TOTAL: {t_step_total*1e6:8.1f} µs")

            if self._callback and i % 10 == 0:
                self._callback({
                    'type': 'progress',
                    'step': i,
                    'total': num_steps,
                    'freq_mhz': freqs[i] / 1e6,
                })

        if dropped_steps > 0:
            print(f"[sfcw] WARNING: {dropped_steps}/{num_steps} steps had incomplete captures")

        # === TIMING: Post-processing ===
        t_post_start = time.perf_counter()

        # Phase-reference division: cancels TX and RX PLL phase offsets
        t0 = time.perf_counter()
        ref_mag = np.abs(h_reference)
        valid = ref_mag > 1e-10
        h_cal = np.zeros(num_steps, dtype=np.complex128)
        h_cal[valid] = h_signal[valid] / h_reference[valid]
        t_phase_cal = time.perf_counter() - t0

        # Background subtraction: removes TX->RX coupling and static clutter
        t0 = time.perf_counter()
        if self._capture_background:
            self._background = h_cal.copy()
            self._capture_background = False
        self._last_h_cal = h_cal.copy()
        t_bg_sub = time.perf_counter() - t0

        t_post_total = time.perf_counter() - t_post_start

        # === TIMING: Final processing (IFFT, etc.) ===
        t_final_start = time.perf_counter()
        result = self._process_h_cal(h_cal)
        t_final_process = time.perf_counter() - t_final_start

        # === TIMING: Print summary ===
        t_sweep_total = time.perf_counter() - t_sweep_start

        if enable_timing:
            print(f"\n{'='*70}")
            print(f"[TIMING SUMMARY] Sweep complete")
            print(f"{'='*70}")
            avg_step = np.mean(all_step_times)
            avg_retune = np.mean(all_retune_times)
            avg_settle = np.mean(all_settle_times)
            avg_capture = np.mean(all_capture_times)
            avg_process = np.mean(all_process_times)

            print(f"  Per-step averages ({num_steps} steps):")
            print(f"    Retune:      {avg_retune:8.1f} µs  ({avg_retune/avg_step*100:4.1f}%)")
            print(f"    Settle:      {avg_settle:8.1f} µs  ({avg_settle/avg_step*100:4.1f}%)")
            print(f"    Capture:     {avg_capture:8.1f} µs  ({avg_capture/avg_step*100:4.1f}%)")
            print(f"    Process:     {avg_process:8.1f} µs  ({avg_process/avg_step*100:4.1f}%)")
            print(f"    Step total:  {avg_step:8.1f} µs")
            print(f"")
            print(f"  Post-processing:")
            print(f"    Phase calib: {t_phase_cal*1e6:8.1f} µs")
            print(f"    Background:  {t_bg_sub*1e6:8.1f} µs")
            print(f"    Post total:  {t_post_total*1e6:8.1f} µs")
            print(f"")
            print(f"  Final processing (IFFT, etc.):")
            print(f"    Time:        {t_final_process*1e6:8.1f} µs")
            print(f"")
            print(f"  TOTAL SWEEP TIME: {t_sweep_total*1e6:10.1f} µs  ({t_sweep_total*1000:6.2f} ms)")
            print(f"{'='*70}\n")

        return result

    def _perform_sweep_raw(self):
        """Like _perform_sweep but returns raw h_cal array for averaging."""
        with self._lock:
            start = self.start_freq
            stop = self.stop_freq
            step = self.step_size
            settle = self.settle_time
            num_buffers = self.num_buffers

        num_steps = int((stop - start) / step) + 1
        freqs = np.linspace(start, stop, num_steps).astype(np.int64)
        h_signal = np.zeros(num_steps, dtype=np.complex128)
        h_reference = np.zeros(num_steps, dtype=np.complex128)

        dev_ptr = self.driver.device.dev[0]
        tx_ch = bladerf.CHANNEL_TX(0)
        rx_ch = bladerf.CHANNEL_RX(0)

        use_qt = (self._use_quick_tune and self._qt_profiles_rx is not None
                  and len(self._qt_profiles_rx) == num_steps)
        settle_count = 10 if use_qt else 2

        dropped_steps = 0

        for i in range(num_steps):
            if self._stop_event.is_set():
                return None

            f = int(freqs[i])
            if use_qt:
                libbladeRF.bladerf_schedule_retune(dev_ptr, rx_ch, 0, f, self._qt_profiles_rx[i])
                libbladeRF.bladerf_schedule_retune(dev_ptr, tx_ch, 0, f, self._qt_profiles_tx[i])
            else:
                libbladeRF.bladerf_set_frequency(dev_ptr, tx_ch, f)
                libbladeRF.bladerf_set_frequency(dev_ptr, rx_ch, f)

            with self._rx_cond:
                target_seq = self._rx_seq + settle_count
                while self._rx_seq < target_seq:
                    if not self._rx_cond.wait(timeout=1.0):
                        break

            rx1_bufs = []
            rx2_bufs = []
            with self._rx_cond:
                last_seq = self._rx_seq

            for _ in range(num_buffers):
                with self._rx_cond:
                    while self._rx_seq <= last_seq:
                        if not self._rx_cond.wait(timeout=1.0):
                            break
                    if self._rx_seq > last_seq:
                        rx1_bufs.append(self._rx_latest[0])
                        rx2_bufs.append(self._rx_latest[1])
                        last_seq = self._rx_seq

            captured = len(rx1_bufs)
            if captured > 0:
                sig_arr = np.array(rx1_bufs, dtype=np.float64)
                ref_arr = np.array(rx2_bufs, dtype=np.float64)
                sig_cplx = (sig_arr[:, 0::2] + 1j * sig_arr[:, 1::2]) * self._ref_tone_scaled
                ref_cplx = (ref_arr[:, 0::2] + 1j * ref_arr[:, 1::2]) * self._ref_tone_scaled
                h_signal[i] = sig_cplx.mean()
                h_reference[i] = ref_cplx.mean()
            else:
                dropped_steps += 1

        ref_mag = np.abs(h_reference)
        valid = ref_mag > 1e-10
        h_cal = np.zeros(num_steps, dtype=np.complex128)
        h_cal[valid] = h_signal[valid] / h_reference[valid]

        return h_cal

    def _process_h_cal(self, h_cal):
        num_steps = len(h_cal)
        start = self.start_freq
        stop = self.stop_freq
        step = self.step_size

        if self._background is not None and len(self._background) == num_steps:
            if self._bg_subtract_mode == 'magnitude':
                mag_diff = np.abs(h_cal) - np.abs(self._background)
                h_cal = mag_diff * np.exp(1j * np.angle(h_cal))
            else:
                h_cal = h_cal - self._background

        phase_raw = np.angle(h_cal)
        phase_unwrapped = np.unwrap(phase_raw)
        coeffs = np.polyfit(np.arange(num_steps), phase_unwrapped, 1)
        residuals = phase_unwrapped - np.polyval(coeffs, np.arange(num_steps))
        phase_std = float(np.std(residuals))

        window = np.hanning(num_steps)
        h_windowed = h_cal * window
        nfft = num_steps * 4
        range_profile = np.fft.ifft(h_windowed, n=nfft)
        magnitude_db = 20 * np.log10(np.abs(range_profile) + 1e-12)

        max_range = SPEED_OF_LIGHT / (2 * step)
        distances = np.linspace(0, max_range, nfft) - self.range_offset

        half = nfft // 2
        magnitude_db = magnitude_db[:half]
        distances = distances[:half]

        valid = distances >= 0
        distances = distances[valid]
        magnitude_db = magnitude_db[valid]

        h_cal_real = h_cal.real.tolist()
        h_cal_imag = h_cal.imag.tolist()

        bscan_flag = self._capture_bscan
        if bscan_flag:
            self._capture_bscan = False
        bscan_bg_flag = self._capture_bscan_bg
        if bscan_bg_flag:
            self._capture_bscan_bg = False

        return {
            'type': 'range_profile',
            'distances': distances.tolist(),
            'magnitudes': magnitude_db.tolist(),
            'h_cal_real': [round(v, 8) for v in h_cal_real],
            'h_cal_imag': [round(v, 8) for v in h_cal_imag],
            'range_resolution': SPEED_OF_LIGHT / (2 * (stop - start)),
            'max_range': max_range / 2,
            'num_steps': num_steps,
            'step_size': step,
            'range_offset': self.range_offset,
            'timestamp': time.time(),
            'bscan_capture': bscan_flag,
            'bscan_bg_capture': bscan_bg_flag,
            'phase_coherence': {
                'phase_std_rad': phase_std,
                'phase_std_deg': float(np.degrees(phase_std)),
                'coherent': phase_std < 0.3,
                'slope_rad_per_step': float(coeffs[0]),
            },
        }
