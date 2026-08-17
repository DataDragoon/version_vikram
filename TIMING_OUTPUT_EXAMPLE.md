# Example Timing Output with Context

This shows what you'll see when you run a sweep with the new timing instrumentation.

---

## Full Example Output:

```
[PROCESS] Configuring hardware...
  → Setting TX/RX gains (TX1=30, RX1=30)
  → Setting sample rate to 10 MHz (bandwidth 8 MHz)
  → Generating CW waveform (100 kHz offset, 0.9 amplitude)
     Time: 1234.5 µs
  → Generating quick_tune profiles (151 frequencies: 2.0-5.0 GHz)
     Purpose: Pre-cache PLL settings to avoid USB round-trips during sweep
     [  0] 2000 MHz: VCO cal + capture state ( 345.2 µs)
     [  1] 2020 MHz: VCO cal + capture state ( 298.7 µs)
     [  2] 2040 MHz: VCO cal + capture state ( 287.3 µs)
     ...
     [149] 4980 MHz: VCO cal + capture state ( 301.2 µs)
     [150] 5000 MHz: VCO cal + capture state ( 295.8 µs)
  ✓ Generated 151 profiles in  45234.5 µs (45.23 ms)

  → Configuring dual-channel mode (TX1+TX2, RX1+RX2)
     Time: 2345.6 µs
  → Setting FPGA tuning mode (hardware-timed frequency changes)
     Time:  123.4 µs
  ✓ Hardware configured in 48937.5 µs (48.94 ms)

[PROCESS] Starting TX/RX streams...
  → Initializing RX condition variable for buffer synchronization
  → Computing reference tone (100 kHz offset, 4096 samples)
     Purpose: Demodulate received IQ data to baseband
     Time:    234.5 µs
  → Starting TX dual-channel stream (TX1=antenna, TX2=reference cable)
     Time:   1234.5 µs
  → Starting RX dual-channel stream (RX1=antenna, RX2=reference cable)
     Buffer size: 4096 samples per channel
     Time:   2345.6 µs
  → Waiting for streams to stabilize (50ms)
     Time:  50123.4 µs
  → Applying gains (must be done AFTER module enable)
     RX1=30dB, RX2=20dB, TX1=30dB, TX2=30dB
     Time:    567.8 µs
  ✓ TX/RX streams active in 54505.8 µs (54.51 ms)

===========================================================================
[SFCW SWEEP] Starting stepped-frequency sweep
===========================================================================

SWEEP CONFIGURATION:
  Frequency range: 2.0 - 5.0 GHz
  Step size: 20.0 MHz
  Number of steps: 151
  Retune method: Quick_tune (pre-cached)
  Settle buffers: 10 @ 10 MHz sample rate
  Buffers per step: 1

STARTING SWEEP...


[STEP 0/150] Frequency: 2000 MHz (2.00 GHz)
  1. Retune TX/RX PLLs to 2000 MHz
     → Method: Quick_tune (pre-cached)
     → Time:     32.1 µs

  2. Wait for PLL to stabilize
     → Waiting for 10 new RX buffers to arrive
     → Purpose: Discard buffers captured during frequency change
     → Time:    234.5 µs

  3. Capture IQ samples
     → Captured 1 buffer(s) of 4096 samples each
     → RX1: Antenna signal, RX2: Reference cable (for phase calibration)
     → Time:    189.3 µs

  4. Process captured data
     → Convert int16 → float64 → complex
     → Multiply by reference tone (demodulate to baseband)
     → Compute mean (correlation)
     → Time:    123.4 µs

  ✓ Step completed in    579.3 µs


[STEP 1/150] Frequency: 2020 MHz (2.02 GHz)
  1. Retune TX/RX PLLs to 2020 MHz
     → Method: Quick_tune (pre-cached)
     → Time:     28.7 µs

  2. Wait for PLL to stabilize
     → Waiting for 10 new RX buffers to arrive
     → Purpose: Discard buffers captured during frequency change
     → Time:    245.6 µs

  3. Capture IQ samples
     → Captured 1 buffer(s) of 4096 samples each
     → RX1: Antenna signal, RX2: Reference cable (for phase calibration)
     → Time:    198.2 µs

  4. Process captured data
     → Convert int16 → float64 → complex
     → Multiply by reference tone (demodulate to baseband)
     → Compute mean (correlation)
     → Time:    115.8 µs

  ✓ Step completed in    588.3 µs

... (steps 2-148 omitted for brevity) ...

[STEP 149/150] Frequency: 4980 MHz (4.98 GHz)
  1. Retune TX/RX PLLs to 4980 MHz
     → Method: Quick_tune (pre-cached)
     → Time:     31.2 µs

  2. Wait for PLL to stabilize
     → Waiting for 10 new RX buffers to arrive
     → Purpose: Discard buffers captured during frequency change
     → Time:    241.3 µs

  3. Capture IQ samples
     → Captured 1 buffer(s) of 4096 samples each
     → RX1: Antenna signal, RX2: Reference cable (for phase calibration)
     → Time:    193.7 µs

  4. Process captured data
     → Convert int16 → float64 → complex
     → Multiply by reference tone (demodulate to baseband)
     → Compute mean (correlation)
     → Time:    119.5 µs

  ✓ Step completed in    585.7 µs


[STEP 150/150] Frequency: 5000 MHz (5.00 GHz)
  1. Retune TX/RX PLLs to 5000 MHz
     → Method: Quick_tune (pre-cached)
     → Time:     29.8 µs

  2. Wait for PLL to stabilize
     → Waiting for 10 new RX buffers to arrive
     → Purpose: Discard buffers captured during frequency change
     → Time:    238.9 µs

  3. Capture IQ samples
     → Captured 1 buffer(s) of 4096 samples each
     → RX1: Antenna signal, RX2: Reference cable (for phase calibration)
     → Time:    191.2 µs

  4. Process captured data
     → Convert int16 → float64 → complex
     → Multiply by reference tone (demodulate to baseband)
     → Compute mean (correlation)
     → Time:    117.3 µs

  ✓ Step completed in    577.2 µs


===========================================================================
[SWEEP SUMMARY] All 151 frequency steps completed
===========================================================================

PER-STEP BREAKDOWN (averaged over 151 steps):

  1. Retune:     30.5 µs  ( 5.2%)
     → Change TX/RX frequency using quick_tune

  2. Settle:    242.3 µs  (41.3%)
     → Wait for PLL stabilization (10 buffers @ 10 MHz sample rate)

  3. Capture:   195.7 µs  (33.4%)
     → Receive 1 buffer(s) of IQ data from RX1+RX2

  4. Process:   118.2 µs  (20.1%)
     → Convert, demodulate, and correlate IQ samples

  Total per step:    586.7 µs

---------------------------------------------------------------------------

POST-PROCESSING (after all steps):

  Phase calibration:    123.4 µs
  → Divide h_signal by h_reference to cancel TX/RX phase offsets

  Background handling:     45.6 µs
  → Copy h_cal for background subtraction

---------------------------------------------------------------------------

FINAL PROCESSING:

  IFFT + range conversion:   1234.5 µs
  → Frequency domain → time domain (range profile)
  → Apply windowing, compute dB magnitude

===========================================================================
TOTAL SWEEP TIME:   90123.4 µs  ( 90.12 ms)
===========================================================================
```

---

## Key Features:

1. **Process descriptions** — Every operation explains WHAT it's doing
2. **Purpose statements** — WHY each step is necessary
3. **Technical details** — Frequencies, buffer counts, sample rates, etc.
4. **Timing data** — Microsecond precision for all operations
5. **Summary statistics** — Averages and percentages at the end

---

## What Each Section Shows:

### **Initialization:**
- Hardware configuration steps with actual values
- Quick_tune profile generation (one-time setup)
- TX/RX stream startup with buffer sizes

### **Per-Step Sweep:**
- Logged for first 5 steps + last 2 steps
- Shows all 4 phases: Retune, Settle, Capture, Process
- Explains the purpose of each phase
- Includes microsecond timing

### **Summary:**
- Averages across all 151 steps
- Percentage breakdown (where time is spent)
- Post-processing steps explained
- Total sweep time

---

**Now you can see both WHAT is happening AND how long it takes!**
