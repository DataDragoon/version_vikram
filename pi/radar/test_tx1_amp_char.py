"""Characterize max TX1 digital amplitude per frequency step.

Uses TX gain = 54 dB, TX2 amp = 0.01, RX gain = 25 dB.
Transmits at a known TX1 amplitude, measures RX1 peak at each frequency,
then calculates the max amplitude that keeps RX1 peak below 0.9.

Since the system is linear: max_amp = target_peak * (test_amp / measured_peak)

Saves a JSON lookup table: {freq_hz: max_tx1_amplitude}
"""

import json
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
CW_OFFSET = 100_000
BUF_SAMPLES = 1024

# Operating point from saturation test
TX_GAIN = 44
RX_GAIN = 25
TX2_AMP = 0.05

# Test TX1 amplitude — moderate value for measurement
TEST_TX1_AMP = 0.3

# Target: RX1 peak should not exceed this (leaves headroom)
TARGET_RX1_PEAK = 0.9

# Number of settle + capture buffers
NUM_SETTLE_BUFFERS = 2
NUM_CAPTURE_BUFFERS = 4


def run_characterization():
    print("=" * 70)
    print("TX1 AMPLITUDE vs FREQUENCY CHARACTERIZATION")
    print(f"Sweep: {START_FREQ/1e9:.1f} - {STOP_FREQ/1e9:.1f} GHz, step {STEP_SIZE/1e6:.0f} MHz")
    print(f"TX gain: {TX_GAIN} dB, RX gain: {RX_GAIN} dB, TX2 amp: {TX2_AMP}")
    print(f"Test TX1 amplitude: {TEST_TX1_AMP}")
    print(f"Target RX1 peak: {TARGET_RX1_PEAK}")
    print("=" * 70)

    device = bladerf.BladeRF()
    dev_ptr = device.dev[0]
    print(f"[OK] bladeRF opened: {device.get_serial()}")

    num_steps = int((STOP_FREQ - START_FREQ) / STEP_SIZE) + 1
    freqs = np.linspace(START_FREQ, STOP_FREQ, num_steps).astype(np.int64)
    print(f"[OK] {num_steps} frequency steps")

    # Reference tone for downconversion
    t = np.arange(BUF_SAMPLES, dtype=np.float64) / SAMPLE_RATE
    ref_tone = np.exp(-1j * 2 * np.pi * CW_OFFSET * t)

    # RX capture state
    rx_lock = threading.Lock()
    rx_latest = [None, None]
    rx_seq = [0]

    # Configure channels
    for ch_idx in range(2):
        tx_ch = bladerf.CHANNEL_TX(ch_idx)
        rx_ch = bladerf.CHANNEL_RX(ch_idx)
        libbladeRF.bladerf_set_frequency(dev_ptr, tx_ch, int(START_FREQ))
        libbladeRF.bladerf_set_sample_rate(dev_ptr, tx_ch, SAMPLE_RATE, ffi.NULL)
        libbladeRF.bladerf_set_bandwidth(dev_ptr, tx_ch, BANDWIDTH, ffi.NULL)
        libbladeRF.bladerf_set_frequency(dev_ptr, rx_ch, int(START_FREQ))
        libbladeRF.bladerf_set_sample_rate(dev_ptr, rx_ch, SAMPLE_RATE, ffi.NULL)
        libbladeRF.bladerf_set_bandwidth(dev_ptr, rx_ch, BANDWIDTH, ffi.NULL)
        libbladeRF.bladerf_set_gain_mode(dev_ptr, rx_ch, MGC)
        libbladeRF.bladerf_set_gain(dev_ptr, rx_ch, RX_GAIN)
        libbladeRF.bladerf_set_gain(dev_ptr, tx_ch, TX_GAIN)

    libbladeRF.bladerf_set_tuning_mode(dev_ptr, TUNING_MODE_FPGA)

    # Generate TX buffer: TX1 at TEST_TX1_AMP, TX2 at TX2_AMP
    n_samples = int(SAMPLE_RATE * 0.01)
    t_buf = np.arange(n_samples, dtype=np.float64) / SAMPLE_RATE
    phase = 2 * np.pi * CW_OFFSET * t_buf
    tx1_i = np.clip(np.cos(phase) * TEST_TX1_AMP * SCALE, -2048, 2047).astype(np.int16)
    tx1_q = np.clip(np.sin(phase) * TEST_TX1_AMP * SCALE, -2048, 2047).astype(np.int16)
    tx2_i = np.clip(np.cos(phase) * TX2_AMP * SCALE, -2048, 2047).astype(np.int16)
    tx2_q = np.clip(np.sin(phase) * TX2_AMP * SCALE, -2048, 2047).astype(np.int16)

    tx_buf = np.empty(n_samples * 4, dtype=np.int16)
    tx_buf[0::4] = tx1_i
    tx_buf[1::4] = tx1_q
    tx_buf[2::4] = tx2_i
    tx_buf[3::4] = tx2_q
    tx_bytes = tx_buf.tobytes()

    # Start TX
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
            print(f"  TX error: {e}")

    tx_thread = threading.Thread(target=tx_loop, daemon=True)
    tx_thread.start()

    # Start RX
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
            print(f"  RX error: {e}")

    rx_thread = threading.Thread(target=rx_loop, daemon=True)
    rx_thread.start()

    # Re-apply gains after enable_module
    time.sleep(0.05)
    for ch_idx in range(2):
        libbladeRF.bladerf_set_gain_mode(dev_ptr, bladerf.CHANNEL_RX(ch_idx), MGC)
        libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_RX(ch_idx), RX_GAIN)
        libbladeRF.bladerf_set_gain(dev_ptr, bladerf.CHANNEL_TX(ch_idx), TX_GAIN)

    time.sleep(0.1)

    # Sweep and measure
    rx1_peaks = np.zeros(num_steps)
    rx1_mags = np.zeros(num_steps)
    rx2_mags = np.zeros(num_steps)

    tx_ch0 = bladerf.CHANNEL_TX(0)
    rx_ch0 = bladerf.CHANNEL_RX(0)

    print(f"\nSweeping {num_steps} steps...")
    for i in range(num_steps):
        f = int(freqs[i])
        libbladeRF.bladerf_set_frequency(dev_ptr, tx_ch0, f)
        libbladeRF.bladerf_set_frequency(dev_ptr, rx_ch0, f)

        # Settle
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

            if rx1 is None:
                continue

            # RX1 peak
            rx1_abs = np.abs(rx1.astype(np.float64)) / 2047.0
            step_peak = np.max(rx1_abs)
            if step_peak > peak_max:
                peak_max = step_peak

            # Signal magnitudes via downconversion
            i1 = rx1[0::2].astype(np.float64) / 2047.0
            q1 = rx1[1::2].astype(np.float64) / 2047.0
            sig_accum += np.mean((i1 + 1j * q1) * ref_tone)

            i2 = rx2[0::2].astype(np.float64) / 2047.0
            q2 = rx2[1::2].astype(np.float64) / 2047.0
            ref_accum += np.mean((i2 + 1j * q2) * ref_tone)

        rx1_peaks[i] = peak_max
        rx1_mags[i] = np.abs(sig_accum / NUM_CAPTURE_BUFFERS)
        rx2_mags[i] = np.abs(ref_accum / NUM_CAPTURE_BUFFERS)

        if i % 50 == 0:
            print(f"  Step {i}/{num_steps} ({freqs[i]/1e9:.2f} GHz) — "
                  f"RX1 peak: {peak_max:.4f}, RX1 mag: {rx1_mags[i]:.4f}, RX2 mag: {rx2_mags[i]:.4f}")

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
    device.close()
    print("\n[OK] Device closed.")

    # Calculate max TX1 amplitude per frequency
    # Linear relationship: if test_amp gives measured_peak, then max_amp = target * test_amp / measured_peak
    # Cap at 1.0 (DAC max)
    max_tx1_amp = np.zeros(num_steps)
    for i in range(num_steps):
        if rx1_peaks[i] > 0.001:
            max_tx1_amp[i] = min(1.0, TARGET_RX1_PEAK * TEST_TX1_AMP / rx1_peaks[i])
        else:
            max_tx1_amp[i] = 1.0

    # Build lookup table
    lookup = {
        'metadata': {
            'tx_gain_db': TX_GAIN,
            'rx_gain_db': RX_GAIN,
            'tx2_amplitude': TX2_AMP,
            'test_tx1_amplitude': TEST_TX1_AMP,
            'target_rx1_peak': TARGET_RX1_PEAK,
            'start_freq_hz': int(START_FREQ),
            'stop_freq_hz': int(STOP_FREQ),
            'step_size_hz': int(STEP_SIZE),
            'num_steps': num_steps,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        },
        'freq_hz': [int(f) for f in freqs],
        'max_tx1_amplitude': [round(float(a), 4) for a in max_tx1_amp],
        'measured_rx1_peak': [round(float(p), 4) for p in rx1_peaks],
        'measured_rx1_mag': [round(float(m), 4) for m in rx1_mags],
        'measured_rx2_mag': [round(float(m), 4) for m in rx2_mags],
    }

    out_path = '/home/sfr/version0/pi/radar/tx1_amp_lut.json'
    with open(out_path, 'w') as f:
        json.dump(lookup, f, indent=2)
    print(f"\n[SAVED] {out_path}")

    # Print summary
    print(f"\n{'='*70}")
    print("RESULTS SUMMARY")
    print(f"{'='*70}")
    print(f"{'Freq (GHz)':<12} {'RX1 Peak':<12} {'Max TX1 Amp':<14} {'RX1 Mag':<12} {'RX2 Mag':<12}")
    print("-" * 62)
    for i in range(0, num_steps, 50):
        print(f"{freqs[i]/1e9:<12.2f} {rx1_peaks[i]:<12.4f} {max_tx1_amp[i]:<14.4f} "
              f"{rx1_mags[i]:<12.4f} {rx2_mags[i]:<12.4f}")
    i = num_steps - 1
    print(f"{freqs[i]/1e9:<12.2f} {rx1_peaks[i]:<12.4f} {max_tx1_amp[i]:<14.4f} "
          f"{rx1_mags[i]:<12.4f} {rx2_mags[i]:<12.4f}")

    print(f"\nAmplitude range: {np.min(max_tx1_amp):.4f} - {np.max(max_tx1_amp):.4f}")
    print(f"Steps at max (1.0): {np.sum(max_tx1_amp >= 1.0)}/{num_steps}")
    print(f"Steps needing reduction: {np.sum(max_tx1_amp < 1.0)}/{num_steps}")

    # Check if reference channel is usable
    min_rx2 = np.min(rx2_mags)
    max_rx2 = np.max(rx2_mags)
    print(f"\nReference channel (RX2) magnitude range: {min_rx2:.4f} - {max_rx2:.4f}")
    low_ref = np.sum(rx2_mags < 0.001)
    print(f"Steps with RX2 < 0.001 (potentially too low for reference): {low_ref}/{num_steps}")


if __name__ == '__main__':
    run_characterization()
