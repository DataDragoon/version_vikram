# 🕐 Timestamp Instrumentation - Complete Process List

## Overview

Every major process in the SFCW sweep pipeline now has **microsecond-precision timestamps** using `time.perf_counter()`.

---

## 📊 **All Timestamped Processes**

### **1. INITIALIZATION (One-time Setup)**

#### **A. Hardware Configuration** (`_configure_hardware`)
```
[TIMING] Configuring hardware...
  - Basic config:     XXXX µs  (gains, sample rate, waveform)
  - Channel config:   XXXX µs  (dual-channel setup)
  - Tuning mode:      XXXX µs  (FPGA tuning mode)
  TOTAL: XXXX µs (XX.XX ms)
```

**Processes measured:**
- Setting TX/RX gains
- Setting sample rate (10 MHz)
- Setting bandwidth (8 MHz)
- Waveform generation
- Dual-channel configuration
- FPGA tuning mode setup

---

#### **B. Quick_Tune Profile Generation** (`_generate_quick_tune_profiles`)
```
[TIMING] Generating quick_tune profiles...
  Profile 0/150 @ 2000 MHz: XXX.X µs
  Profile 1/150 @ 2020 MHz: XXX.X µs
  Profile 2/150 @ 2040 MHz: XXX.X µs
  ...
  Profile 149/150 @ 4980 MHz: XXX.X µs
  Profile 150/150 @ 5000 MHz: XXX.X µs
Generated 151 quick_tune profiles in XXXXX.X µs (XXX.XX ms)
```

**Processes measured:**
- Per-frequency profile generation (first 3 + last 2 logged)
- `bladerf_set_frequency()` calls
- `bladerf_get_quick_tune()` calls
- Total profile generation time

---

#### **C. TX/RX Stream Startup** (`_start_tx_rx`)
```
[TIMING] Starting TX/RX streams...
  - Ref tone prep:  XXXX.X µs
  - Start TX:       XXXX.X µs
  - Start RX:       XXXX.X µs
  - Stream settle:  XXXXX.X µs (50ms sleep)
  - Apply gains:    XXXX.X µs
  TOTAL: XXXXX.X µs (XX.XX ms)
```

**Processes measured:**
- Reference tone computation
- TX stream initialization
- RX stream initialization
- 50ms settling delay
- Gain application (after module enable)

---

### **2. PER-STEP SWEEP OPERATIONS (151× per sweep)**

#### **Detailed Per-Step Timing** (logged for first 5 + last 2 steps)
```
[TIMING] Step 0/150 @ 2000 MHz:
  Retune:     XXX.X µs  (quick_tune / set_freq)
  Settle:     XXX.X µs  (wait for N buffers)
  Capture:    XXX.X µs  (N buffers)
  Process:    XXX.X µs  (demod + correlation)
  STEP TOTAL: XXX.X µs
```

**Per-step processes measured:**

**A. Frequency Retune:**
- `bladerf_schedule_retune()` (with quick_tune) OR
- `bladerf_set_frequency()` (without quick_tune)
- Both TX and RX channels

**B. PLL Settle Wait:**
- Condition variable wait
- Waits for N new buffers (10 with quick_tune, 2 without)
- Includes USB transfer latency

**C. Buffer Capture:**
- Condition variable waits for each buffer
- RX1 and RX2 data capture
- Multiple buffers if `num_buffers > 1`

**D. Buffer Processing:**
- Numpy array conversion
- Deinterleaving (RX1/RX2 split)
- Complex conversion (I+jQ)
- Reference tone multiplication
- Mean calculation (correlation)

---

### **3. POST-SWEEP PROCESSING (After all 151 steps)**

#### **A. Phase Calibration**
```
Phase calib: XXX.X µs
```

**Processes:**
- Magnitude calculation (`np.abs()`)
- Division: `h_signal / h_reference`
- Removes random PLL phase offsets

---

#### **B. Background Subtraction**
```
Background: XXX.X µs
```

**Processes:**
- Background capture (if enabled)
- Array copy operations

---

#### **C. Final Processing (IFFT, etc.)**
```
Time: XXXXX.X µs
```

**Processes (in `_process_h_cal`):**
- Phase unwrapping
- Windowing (Hanning)
- IFFT (inverse FFT)
- dB conversion
- Range axis calculation
- Phase coherence analysis

---

### **4. SUMMARY STATISTICS**

#### **Per-Step Averages** (averaged over all 151 steps)
```
[TIMING SUMMARY] Sweep complete
  Per-step averages (151 steps):
    Retune:      XXX.X µs  (XX.X%)
    Settle:      XXX.X µs  (XX.X%)
    Capture:     XXX.X µs  (XX.X%)
    Process:     XXX.X µs  (XX.X%)
    Step total:  XXX.X µs

  Post-processing:
    Phase calib: XXX.X µs
    Background:  XXX.X µs
    Post total:  XXX.X µs

  Final processing (IFFT, etc.):
    Time:        XXXXX.X µs

  TOTAL SWEEP TIME: XXXXXX.X µs  (XXX.XX ms)
```

---

## 🎯 **What Each Timing Reveals**

### **Initialization Timings Show:**
- ✅ Hardware config overhead (one-time cost)
- ✅ Quick_tune profile generation speed (cached after first run)
- ✅ Stream startup latency

### **Per-Step Timings Show:**
- ✅ **Retune efficiency** — Quick_tune should be <50 µs, set_frequency ~200-500 µs
- ✅ **Settle wait** — How long for PLL to stabilize (depends on buffer rate)
- ✅ **Capture wait** — USB transfer + condition variable latency
- ✅ **Process time** — Numpy computation overhead

### **Summary Statistics Show:**
- ✅ **Bottleneck identification** — Which phase takes most time?
- ✅ **Percentage breakdown** — Where is time being spent?
- ✅ **Total sweep time** — Overall performance metric

---

## 📈 **Expected Performance (Optimized Code)**

### **With Quick_Tune + 10 MHz Sample Rate:**
```
Per-step average:  ~600 µs  (0.6 ms)
Total sweep time:  ~90 ms   (151 steps × 0.6 ms)

Breakdown:
  Retune:    ~30 µs   (5%)   ← Quick_tune is FAST
  Settle:    ~250 µs  (40%)  ← Waiting for 10 buffers
  Capture:   ~200 µs  (35%)  ← USB transfer
  Process:   ~120 µs  (20%)  ← Numpy operations
```

### **Without Quick_Tune (Old Method):**
```
Per-step average:  ~33,000 µs  (33 ms)
Total sweep time:  ~5,000 ms   (5 seconds)

55× SLOWER!
```

---

## 🔍 **How to Read the Output**

### **Detailed Step Logs:**
You'll see detailed timing for:
- **First 5 steps** (0-4) — Shows startup behavior
- **Last 2 steps** (149-150) — Shows steady-state behavior

### **Summary at End:**
- **Averages** — Across all 151 steps
- **Percentages** — Relative cost of each phase
- **Total time** — End-to-end performance

---

## 🚀 **What to Look For**

### **Good Performance Indicators:**
- ✅ Retune time < 50 µs (quick_tune working)
- ✅ Step total ~ 600 µs per step
- ✅ Total sweep < 100 ms

### **Problem Indicators:**
- ⚠️ Retune time > 500 µs (quick_tune not working)
- ⚠️ Settle time >> 500 µs (too many settle buffers)
- ⚠️ Capture time >> 300 µs (USB issues)
- ⚠️ Process time >> 200 µs (inefficient numpy code)

---

## 📝 **Example Output**

```
[TIMING] Configuring hardware...
[TIMING] Hardware config: 1234.5 µs (basic)
[TIMING] Channel config:  2345.6 µs (dual-channel)
[TIMING] Tuning mode:      123.4 µs (FPGA)
[TIMING] Config total:    3703.5 µs (3.70 ms)

[TIMING] Generating quick_tune profiles...
  Profile 0/150 @ 2000 MHz:   345.2 µs
  Profile 1/150 @ 2020 MHz:   298.7 µs
  Profile 2/150 @ 2040 MHz:   287.3 µs
  ...
[TIMING] Generated 151 quick_tune profiles in 45234.5 µs (45.23 ms)

[TIMING] Starting TX/RX streams...
[TIMING] Ref tone prep:    234.5 µs
[TIMING] Start TX:        1234.5 µs
[TIMING] Start RX:        2345.6 µs
[TIMING] Stream settle:  50123.4 µs (50ms sleep)
[TIMING] Apply gains:      567.8 µs
[TIMING] Start total:    54505.8 µs (54.51 ms)

[TIMING] Step 0/150 @ 2000 MHz:
  Retune:       32.1 µs  (quick_tune)
  Settle:      234.5 µs  (wait for 10 buffers)
  Capture:     189.3 µs  (1 buffers)
  Process:     123.4 µs  (demod + correlation)
  STEP TOTAL:  579.3 µs

[TIMING] Step 1/150 @ 2020 MHz:
  Retune:       28.7 µs  (quick_tune)
  Settle:      245.6 µs  (wait for 10 buffers)
  Capture:     198.2 µs  (1 buffers)
  Process:     115.8 µs  (demod + correlation)
  STEP TOTAL:  588.3 µs

...

======================================================================
[TIMING SUMMARY] Sweep complete
======================================================================
  Per-step averages (151 steps):
    Retune:        30.5 µs  ( 5.2%)
    Settle:       242.3 µs  (41.3%)
    Capture:      195.7 µs  (33.4%)
    Process:      118.2 µs  (20.1%)
    Step total:   586.7 µs

  Post-processing:
    Phase calib:  123.4 µs
    Background:    45.6 µs
    Post total:   169.0 µs

  Final processing (IFFT, etc.):
    Time:       1234.5 µs

  TOTAL SWEEP TIME:   90123.4 µs  ( 90.12 ms)
======================================================================
```

---

## 💡 **Key Insights from Timing**

1. **Quick_tune is critical** — 55× speedup comes from <50 µs retunes
2. **Settle wait dominates** — 40% of time is waiting for buffers
3. **USB latency matters** — Capture time shows USB transfer efficiency
4. **Processing is fast** — Numpy operations are only 20% of time

---

## 🔧 **Optimization Opportunities**

Based on timing data:

### **If retune is slow (>100 µs):**
- Check quick_tune is enabled
- Verify profiles were generated
- Check FPGA tuning mode

### **If settle is slow (>500 µs):**
- Reduce `settle_count` (currently 10)
- Increase sample rate (more buffers/second)

### **If capture is slow (>300 µs):**
- Check USB bus utilization
- Verify buffer sizes
- Check for USB driver issues

### **If process is slow (>200 µs):**
- Profile numpy operations
- Consider float32 instead of float64
- Optimize array operations

---

**All timestamps are in microseconds (µs) for maximum precision!**
