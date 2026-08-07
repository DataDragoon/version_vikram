"""Characterize TX gain ceiling for reference channel saturation.

Sweeps 1-6 GHz at 10 MHz steps for each (tx_gain, tx2_amplitude) combo.
Measures RX2 (reference) normalized amplitude to find where saturation occurs.
TX2 digital amplitudes tested: 0.01, 0.05, 0.1
RX gain fixed at 25 dB for both channels.

Saturation = normalized sample magnitude >= 0.95 (i.e. >=1945/2047)
"""

import sys
import time
import threading
import numpy as np
import bladerf
from bladerf._bladerf import ChannelLayout, Format, ffi, libbladeRF

SCALE = 2047
MGC = libbladeRF.BLADERF_GAIN_MGC
TUNING_MODE_FPGA = libbladeRF.BLADERF_TUNING_MODE_FPGA

START_FREQ = 1_000_000_000
STOP_FREQ = 6_000_000_000
STEP_SIZE = 10_000_000
SAMPLE_RATE = 2_000_000
BANDWIDTH = 1_500_000
RX_GAIN = 25
CW_OFFSET = 100_000
NUM_SETTLE_BUFFERS = 2
NUM_CAPTURE_BUFFERS = 4
BUF_SAMPLES = 1024

SATURATION_THRESHOLD = 0.95
TX2_AMPLITUDES = [0.01, 0.05, 0.1]
TX_GAINS_TO_TEST = list(range(20, 67, 2))  # 20 to 66 dB in 2 dB steps


def run_test():
    print("=" * 70)
    print("TX GAIN SATURATION CHARACTERIZATION")
    print(f"Sweep: {START_FREQ/1e9:.1f} - {STOP_FREQ/1e9:.1f} GHz, step {STEP_SIZE/1e6:.0f} MHz")
    print(f"RX gain: {RX_GAIN} dB (both channels)")
    print(f"TX2 amplitudes to test: {TX2_AMPLITUDES}")
    print(f"TX gains to test: {TX_GAINS_TO_TEST[0]} - {TX_GAINS_TO_TEST[-1]} dB")
    print("=" * 70)

    device = bladerf.BladeRF()
    dev_ptr = device.dev[0]
    print(f"[OK] bladeRF opened: {device.get_serial()}")

    num_steps = int((STOP_FREQ - START_FREQ) / STEP_SIZE) + 1
    print(f"[OK] {num_steps} frequency steps per sweep")

    # Reference tone for downconversion
    t = np.arange(BUF_SAMPLES, dtype=np.float64) / SAMPLE_RATE
    ref_tone = np.exp(-1j * 2 * np.pi * CW_OFFSET * t)

    # RX capture state
    rx_lock = threading.Lock()
    rx_latest = [None, None]
    rx_seq = [0]

    def rx_callback(rx1_iq, rx2_iq):
        with rx_lock:
            rx_latest[0] = rx1_iq
            rx_latest[1] = rx2_iq
            rx_seq[0] += 1

    results = {}

    for tx2_amp in TX2_AMPLITUDES:
        print(f"\n{'='*70}")
        print(f"TESTING TX2 AMPLITUDE = {tx2_amp}")
        print(f"{'='*70}")

        results[tx2_amp] = {}
        saturation_found_at = None

        for tx_gain in TX_GAINS_TO_TEST:
            if saturation_found_at is not None:
                print(f"  TX gain {tx_gain} dB — SKIPPED (already saturated at {saturation_found_at} dB)")
                results[tx2_amp][tx_gain] = {'status': 'skipped'}
                continue

            print(f"\n  TX gain = {tx_gain} dB, TX2 amp = {tx2_amp}...")

            # Configure channels
            device.Channel(bladerf.CHANNEL_TX(0)).frequency = START_FREQ
            device.Channel(bladerf.CHANNEL_TX(0)).sample_rate = SAMPLE_RATE
            device.Channel(bladerf.CHANNEL_TX(0)).bandwidth = BANDWIDTH

            # Set up dual channel via low-level API
            for ch_idx in range(2):
                tx_ch = bladerf.CHANNEL_TX(ch_idx)
                rx_ch = bladerf.CHANNEL_RX(ch_idx)
                libbladeRF.bladerf_set_frequency(dev_ptr, tx_ch, START_FREQ)
                libbladeRF.bladerf_set_sample_rate(dev_ptr, tx_ch, SAMPLE_RATE, ffi.NULL)
                libbladeRF.bladerf_set_bandwidth(dev_ptr, tx_ch, BANDWIDTH, ffi.NULL)
                libbladeRF.bladerf_set_frequency(dev_ptr, rx_ch, START_FREQ)
                libbladeRF.bladerf_set_sample_rate(dev_ptr, rx_ch, SAMPLE_RATE, ffi.NULL)
                libbladeRF.bladerf_set_bandwidth(dev_ptr, rx_ch, BANDWIDTH, ffi.NULL)
                libbladeRF.bladerf_set_gain_mode(dev_ptr, rx_ch, MGC)
                libbladeRF.bladerf_set_gain(dev_ptr, rx_ch, RX_GAIN)
                libbladeRF.bladerf_set_gain(dev_ptr, tx_ch, tx_gain)

            libbladeRF.bladerf_set_tuning_mode(dev_ptr, TUNING_MODE_FPGA)

            # Generate TX buffer: TX1 at full amplitude, TX2 at tx2_amp
            n_samples = int(SAMPLE_RATE * 0.01)
            t_buf = np.arange(n_samples, dtype=np.float64) / SAMPLE_RATE
            phase = 2 * np.pi * CW_OFFSET * t_buf
            tx1_i = np.clip(np.cos(phase) * 0.9 * SCALE, -2048, 2047).astype(np.int16)
            tx1_q = np.clip(np.sin(phase) * 0.9 * SCALE, -2048, 2047).astype(np.int16)
            tx2_i = np.clip(np.cos(phase) * tx2_amp * SCALE, -2048, 2047).astype(np.int16)
            tx2_q = np.clip(np.sin(phase) * tx2_amp * SCALE, -2048, 2047).astype(np.int16)

            # Interleave: [TX1_I, TX1_Q, TX2_I, TX2_Q, ...]
            tx_buf = np.empty(n_samples * 4, dtype=np.int16)
            tx_buf[0::4] = tx1_i
            tx_buf[1::4] = tx1_q
            tx_buf[2::4] = tx2_i
            tx_buf[3::4] = tx2_q
            tx_bytes = tx_buf.tobytes()

            # Start TX dual
            device.sync_config(
                layout=ChannelLayout.TX_X2,
                fmt=Format.SC16_Q11,
                num_buffers=16,
                buffer_size=4096,
                num_transfers=8,
                stream_timeout=3500
            )
            device.enable_module(bladerf.CHANNEL_TX(0), True)
            device.enable_module(bladerf.CHANNEL_TX(1), True)

            tx_stop = threading.Event()

            def tx_loop():
                try:
                    while not tx_stop.is_set():
                        device.sync_tx(tx_bytes, n_samples)
                except Exception as e:
                    print(f"    TX error: {e}")

            tx_thread = threading.Thread(target=tx_loop, daemon=True)
            tx_thread.start()

            # Start RX dual
            device.sync_config(
                layout=ChannelLayout.RX_X2,
                fmt=Format.SC16_Q11,
                num_buffers=16,
                buffer_size=4096,
                num_transfers=8,
                stream_timeout=3500
            )
            device.enable_module(bladerf.CHANNEL_RX(0), True)
            device.enable_module(bladerf.CHANNEL_RX(1), True)

            rx_seq[0] = 0
            rx_stop = threading.Event()

            def rx_loop():
                buf = bytearray(BUF_SAMPLES * 2 * 2 * 2)
                try:
                    while not rx_stop.is_set():
                        device.sync_rx(buf, BUF_SAMPLES)
                        iq = np.frombuffer(buf, dtype=np.int16).copy()
                        rx1 = np.empty(BUF_SAMPLES * 2, dtype=np.int16)
                        rx2 = np.empty(BUF_SAMPLES * 2, dtype=np.int16)
                        rx1[0::2] = iq[0::4]
                        rx1[1::2] = iq[1::4]
                        rx2[0::2] = iq[2::4]
                        rx2[1::2] = iq[3::4]
                        with rx_lock:
                            rx_latest[0] = rx1
                            rx_latest[1] = rx2
                            rx_seq[0] += 1
                except Exception as e:
                    print(f"    RX error: {e}")

            rx_thread = threading.Thread(target=rx_loop, daemon=True)
            rx_thread.start()

            # Re-apply gains after enable_module (it can reset them)
            time.sleep(0.05)
            for ch_idx in range(2):
                libbladeRF.bladerf_set_gain_mode(dev_ptr, bladerf.CHANNEL_RX(ch_idx), MGC)
                libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_RX(ch_idx), RX_GAIN)
                libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_TX(ch_idx), tx_gain)

            time.sleep(0.1)

            # Sweep
            freqs = np.linspace(START_FREQ, STOP_FREQ, num_steps).astype(np.int64)
            rx2_peaks = np.zeros(num_steps)
            rx2_mags = np.zeros(num_steps)
            rx1_mags = np.zeros(num_steps)
            saturated_steps = 0

            tx_ch0 = bladerf.CHANNEL_TX(0)
            rx_ch0 = bladerf.CHANNEL_RX(0)

            for i in range(num_steps):
                f = int(freqs[i])
                libbladeRF.bladerf_set_frequency(dev_ptr, tx_ch0, f)
                libbladeRF.bladerf_set_frequency(dev_ptr, rx_ch0, f)

                # Wait for settle
                with rx_lock:
                    seq_before = rx_seq[0]
                target = seq_before + NUM_SETTLE_BUFFERS
                deadline = time.monotonic() + 1.0
                while True:
                    with rx_lock:
                        if rx_seq[0] >= target:
                            break
                    if time.monotonic() > deadline:
                        break
                    time.sleep(0.0002)

                # Capture
                peak_max = 0.0
                sig_accum = 0j
                ref_accum = 0j
                with rx_lock:
                    last = rx_seq[0]

                for _ in range(NUM_CAPTURE_BUFFERS):
                    deadline = time.monotonic() + 1.0
                    while True:
                        with rx_lock:
                            if rx_seq[0] > last:
                                rx1 = rx_latest[0]
                                rx2 = rx_latest[1]
                                last = rx_seq[0]
                                break
                        if time.monotonic() > deadline:
                            rx1, rx2 = None, None
                            break
                        time.sleep(0.0002)

                    if rx2 is None:
                        continue

                    # Check RX2 peak (raw ADC values)
                    rx2_abs = np.abs(rx2.astype(np.float64)) / 2047.0
                    step_peak = np.max(rx2_abs)
                    if step_peak > peak_max:
                        peak_max = step_peak

                    # Also get signal magnitude via downconversion
                    i2 = rx2[0::2].astype(np.float64) / 2047.0
                    q2 = rx2[1::2].astype(np.float64) / 2047.0
                    ref_accum += np.mean((i2 + 1j * q2) * ref_tone)

                    i1 = rx1[0::2].astype(np.float64) / 2047.0
                    q1 = rx1[1::2].astype(np.float64) / 2047.0
                    sig_accum += np.mean((i1 + 1j * q1) * ref_tone)

                rx2_peaks[i] = peak_max
                rx2_mags[i] = np.abs(ref_accum / NUM_CAPTURE_BUFFERS)
                rx1_mags[i] = np.abs(sig_accum / NUM_CAPTURE_BUFFERS)

                if peak_max >= SATURATION_THRESHOLD:
                    saturated_steps += 1

                if i % 50 == 0:
                    print(f"    Step {i}/{num_steps} ({freqs[i]/1e9:.2f} GHz) — "
                          f"RX2 peak: {peak_max:.3f}, RX1 mag: {np.abs(sig_accum/max(1,NUM_CAPTURE_BUFFERS)):.4f}")

            # Stop TX/RX
            tx_stop.set()
            rx_stop.set()
            tx_thread.join(timeout=2)
            rx_thread.join(timeout=2)
            try:
                device.enable_module(bladerf.CHANNEL_TX(0), False)
                device.enable_module(bladerf.CHANNEL_TX(1), False)
                device.enable_module(bladerf.CHANNEL_RX(0), False)
                device.enable_module(bladerf.CHANNEL_RX(1), False)
            except:
                pass

            # Results
            max_rx2_peak = np.max(rx2_peaks)
            mean_rx2_mag = np.mean(rx2_mags)
            mean_rx1_mag = np.mean(rx1_mags)
            sat_pct = saturated_steps / num_steps * 100

            status = 'SATURATED' if max_rx2_peak >= SATURATION_THRESHOLD else 'OK'
            results[tx2_amp][tx_gain] = {
                'status': status,
                'max_rx2_peak': float(max_rx2_peak),
                'mean_rx2_mag': float(mean_rx2_mag),
                'mean_rx1_mag': float(mean_rx1_mag),
                'saturated_steps': saturated_steps,
                'sat_pct': sat_pct,
            }

            print(f"    RESULT: {status} | max RX2 peak={max_rx2_peak:.3f} | "
                  f"mean RX2 mag={mean_rx2_mag:.4f} | mean RX1 mag={mean_rx1_mag:.4f} | "
                  f"saturated steps: {saturated_steps}/{num_steps} ({sat_pct:.1f}%)")

            if status == 'SATURATED':
                saturation_found_at = tx_gain

            time.sleep(0.2)

    # Summary
    print("\n\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'TX2 Amp':<10} {'Max TX Gain (no sat)':<25} {'RX1 mag at max':<20} {'RX2 mag at max':<20}")
    print("-" * 70)
    for tx2_amp in TX2_AMPLITUDES:
        max_safe_gain = None
        for tx_gain in TX_GAINS_TO_TEST:
            r = results[tx2_amp].get(tx_gain, {})
            if r.get('status') == 'OK':
                max_safe_gain = tx_gain
        if max_safe_gain:
            r = results[tx2_amp][max_safe_gain]
            print(f"{tx2_amp:<10} {max_safe_gain:<25} {r['mean_rx1_mag']:<20.4f} {r['mean_rx2_mag']:<20.4f}")
        else:
            print(f"{tx2_amp:<10} {'ALL SATURATED':<25}")

    print("\nDetailed per-amplitude breakdown:")
    for tx2_amp in TX2_AMPLITUDES:
        print(f"\n  TX2 amplitude = {tx2_amp}:")
        for tx_gain in TX_GAINS_TO_TEST:
            r = results[tx2_amp].get(tx_gain, {})
            if r.get('status') == 'skipped':
                continue
            marker = ' <<<' if r.get('status') == 'SATURATED' else ''
            print(f"    TX gain {tx_gain:2d} dB: peak={r.get('max_rx2_peak', 0):.3f} "
                  f"rx2_mag={r.get('mean_rx2_mag', 0):.4f} rx1_mag={r.get('mean_rx1_mag', 0):.4f}{marker}")

    device.close()
    print("\n[DONE] Device closed.")


if __name__ == '__main__':
    run_test()
