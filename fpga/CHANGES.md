# Half-Adder FPGA Integration - Complete Change Log

This document tracks ALL changes made to implement a half-adder circuit in bladeRF FPGA.

**Date:** August 13, 2026  
**Device:** bladeRF2 Micro A9 (301 KLE FPGA)  
**Goal:** Integrate half-adder accessible via GPIO from Raspberry Pi

---

## 📁 Files Added

### In `version_vikram` Repository

#### Verilog HDL Files
- **`half_adder.v`**
  - Location: `C:\Users\1109h\bladeRF\hdl\fpga\platforms\bladerf-micro\vhdl\half_adder.v`
  - Purpose: Basic half-adder logic (A XOR B for SUM, A AND B for COUT)
  - Copied from: `C:\Users\1109h\AppData\Local\quartus\half_adder.v`

- **`half_adder_gpio.v`**
  - Location: `C:\Users\1109h\bladeRF\hdl\fpga\platforms\bladerf-micro\vhdl\half_adder_gpio.v`
  - Purpose: GPIO wrapper - maps 32-bit GPIO bus to half-adder inputs/outputs
  - GPIO Mapping:
    - Input bit 0 → A
    - Input bit 1 → B
    - Output bit 2 → SUM
    - Output bit 3 → COUT

#### Test Programs (C)
- **`pi/test_half_adder_c.c`**
  - Automated test program (tests all 4 input combinations)
  - Uses `bladerf_expansion_gpio_*` functions
  - Compile: `gcc test_half_adder_c.c -o test_half_adder -lbladeRF`

- **`pi/test_gpio_interactive.c`**
  - Interactive GPIO debugger
  - Commands: r (read), w (write), t (test), q (quit)
  - Compile: `gcc test_gpio_interactive.c -o test_gpio_interactive -lbladeRF`

- **`pi/test_expansion_gpio_direct.c`**
  - Direct backend test using `nios_expansion_gpio_*` functions
  - Bypasses board layer to test NIOS backend directly
  - Compile: `gcc test_expansion_gpio_direct.c -o test_expansion_gpio_direct -lbladeRF`

#### Documentation
- **`fpga/QUICKSTART.md`**
  - Complete step-by-step guide
  - Build instructions for Quartus 20.1.1
  - Troubleshooting reference
  - Test procedures

- **`fpga/CHANGES.md`** (this file)
  - Complete change log
  - All files modified
  - All lessons learned

#### FPGA Images
- **`fpga/custom_images/half_adder_bladerf_a9.rbf`** (13 MB)
  - Final working FPGA image for bladeRF2 A9
  - Includes NIOS II firmware with memory initialization files
  - Ready for deployment

---

## 📝 Files Modified

### In `bladeRF` HDL Repository

#### 1. `hdl/fpga/platforms/bladerf-micro/bladerf-hosted.qip`

**Lines added at end:**
```tcl
set_global_assignment -name VERILOG_FILE [file normalize [file join $here vhdl/half_adder.v]]
set_global_assignment -name VERILOG_FILE [file normalize [file join $here vhdl/half_adder_gpio.v]]
```

**Purpose:** Register Verilog files with Quartus project

---

#### 2. `hdl/fpga/platforms/bladerf-micro/vhdl/bladerf-hosted.vhd`

**Modification A: Component Declaration (around line 183, BEFORE `begin`)**

Added:
```vhdl
signal wbm_wb_cyc_o : std_logic;

-- Half-adder component declaration
component half_adder_gpio
    port (
        gpio_in  : in  std_logic_vector(31 downto 0);
        gpio_out : out std_logic_vector(31 downto 0)
    );
end component;

signal half_adder_out : std_logic_vector(31 downto 0);

begin
```

**Purpose:** Declare half-adder component and internal signal

---

**Modification B: Instantiation and GPIO Synchronizer Fix (around line 990)**

Replaced:
```vhdl
generate_sync_xb_gpio_in : for i in exp_gpio'range generate
    U_sync_xb_gpio_in : entity work.synchronizer
      port map (
        reset => '0',
        clock => sys_clock,
        async => exp_gpio(i),
        sync  => nios_xb_gpio_in(i)
      );
end generate;
```

With:
```vhdl
-- Instantiate half-adder
U_half_adder : half_adder_gpio
    port map (
        gpio_in  => nios_xb_gpio_out,
        gpio_out => half_adder_out
    );

-- Override GPIO inputs with half-adder outputs (bits 3:2)
nios_xb_gpio_in(3 downto 2) <= half_adder_out(3 downto 2);

-- Synchronize GPIO inputs, but SKIP bits 2 and 3 (used by half-adder)
generate_sync_xb_gpio_in : for i in exp_gpio'range generate
    skip_half_adder_bits: if (i /= 2 and i /= 3) generate
        U_sync_xb_gpio_in : entity work.synchronizer
          generic map (
            RESET_LEVEL => '0'
          ) port map (
            reset => '0',
            clock => sys_clock,
            async => exp_gpio(i),
            sync  => nios_xb_gpio_in(i)
          );
    end generate skip_half_adder_bits;
end generate;
```

**Purpose:**
1. Instantiate half-adder logic
2. Connect GPIO write signals (nios_xb_gpio_out) to half-adder inputs
3. Route half-adder outputs back to GPIO read signals (nios_xb_gpio_in)
4. Fix multiple driver error by excluding bits 2,3 from synchronizer

**Critical fix:** The conditional generate `if (i /= 2 and i /= 3)` prevents VHDL multiple driver error

---

#### 3. `hdl/quartus/work/bladerf-micro-A9-hosted/bladeRF_nios_bsp/Makefile`

**Line 65 changed:**

From:
```makefile
ABS_BSP_ROOT := $(shell pwd)
```

To:
```makefile
ABS_BSP_ROOT := C:/Users/1109h/bladeRF/hdl/quartus/work/bladerf-micro-A9-hosted/bladeRF_nios_bsp
```

**Purpose:** Fix MSYS path issue - `$(shell pwd)` returns `/c/Users/...` which Windows-native make.exe can't handle

**Why this was needed:** Git Bash uses MSYS path translation, but Intel's NIOS make.exe is Windows-native

---

#### 4. `hdl/quartus/build_bladerf.sh`

**Line endings fixed:**

```bash
sed -i 's/\r$//' build_bladerf.sh
```

**Purpose:** Convert CRLF (Windows) to LF (Unix) line endings so bash can execute the script

---

### In `version_vikram` Repository

#### 5. `fpga/QUICKSTART.md`

**Multiple updates:**
- Added "ACTUAL WORKING BUILD PROCESS" section
- Updated build commands for A9 FPGA size
- Added BSP Makefile fix instructions
- Added mem_init generation step
- Added troubleshooting for all errors encountered
- Updated test commands to use C programs
- Added git push commands

---

## 🗑️ Files Removed

- **`pi/test_half_adder_fpga.py`** - Removed (Python bladeRF bindings don't expose GPIO)
- **`pi/manual_half_adder_test.py`** - Removed (same reason)

**Why removed:** The bladeRF Python API doesn't have GPIO methods. Must use C API with libbladeRF.

---

## 🔧 Build Process Changes

### Tools Required
1. **Quartus Prime 20.1.1** (NOT 25.1 - NIOS II deprecated in newer versions)
2. **Git Bash** (for build scripts)
3. **gcc** (for compiling test programs on Pi)

### Environment Variables
```bash
export QUARTUS_ROOTDIR="/c/intelFPGA_lite/20.1/quartus"
export QUARTUS_BINDIR="/c/intelFPGA_lite/20.1/quartus/bin64"
export SOPC_KIT_NIOS2="/c/intelFPGA_lite/20.1/nios2eds"
export PATH="/c/intelFPGA_lite/20.1/nios2eds/bin/gnu/H-x86_64-mingw32/bin:$PATH"
export PATH="/c/intelFPGA_lite/20.1/quartus/bin64:$PATH"
export PATH="/c/intelFPGA_lite/20.1/quartus/sopc_builder/bin:$PATH"
export PATH="/c/intelFPGA_lite/20.1/nios2eds/sdk2/bin:$PATH"
```

### Build Commands (Summary)

1. **Start build** (generates NIOS system, BSP):
   ```bash
   cd /c/Users/1109h/bladeRF/hdl/quartus
   ./build_bladerf.sh -b bladeRF-micro -s A9 -r hosted
   ```

2. **Fix BSP Makefile** (when build fails at make step):
   ```bash
   cd work/bladerf-micro-A9-hosted/bladeRF_nios_bsp
   sed -i 's|ABS_BSP_ROOT := $(shell pwd)|ABS_BSP_ROOT := C:/Users/1109h/bladeRF/hdl/quartus/work/bladerf-micro-A9-hosted/bladeRF_nios_bsp|' Makefile
   make
   ```

3. **Generate memory initialization files**:
   ```bash
   cd /c/Users/1109h/bladeRF/hdl/fpga/platforms/bladerf-micro/software/bladeRF_nios
   make WORKDIR=work/bladerf-micro-A9-hosted mem_init_generate
   ```

4. **Compile FPGA** (takes ~30-40 minutes):
   ```bash
   cd /c/Users/1109h/bladeRF/hdl/quartus/work/bladerf-micro-A9-hosted
   quartus_sh --64bit -t /c/Users/1109h/bladeRF/hdl/fpga/platforms/bladerf-micro/build/bladerf.tcl -projname bladerf -part 5CEBA9F23C8 -platdir /c/Users/1109h/bladeRF/hdl/fpga/platforms/bladerf-micro
   quartus_sh --64bit -t /c/Users/1109h/bladeRF/hdl/quartus/build.tcl -projname bladerf -rev hosted -flow full -stp "" -force false -seed 1
   ```

5. **Copy .rbf file**:
   ```bash
   cp output_files/hosted.rbf /c/Users/1109h/version_vikram/fpga/custom_images/half_adder_bladerf_a9.rbf
   ```

---

## 🐛 Critical Issues Encountered

### Issue 1: FPGA Size Mismatch (MOST CRITICAL)
**Problem:** Built for A4 (49 KLE) but device is A9 (301 KLE)  
**Symptom:** "Detected potentially incorrect FPGA file (length was 2632660, expected 12858972)"  
**Solution:** Check device FPGA size first: `bladeRF-cli -e "info"` → build for correct size

### Issue 2: Missing Memory Initialization Files
**Problem:** NIOS software build failed → no mem_init files → 2.6 MB .rbf instead of 13 MB  
**Symptom:** .rbf file too small, device rejects it  
**Solution:** Fix BSP Makefile path issue, build NIOS software manually

### Issue 3: BSP Makefile MSYS Path Issue
**Problem:** `$(shell pwd)` returns `/c/Users/...` which Windows make.exe can't parse  
**Symptom:** "make: *** No rule to make target `/c/Users/.../system.h'"  
**Solution:** Hardcode `ABS_BSP_ROOT` with Windows path format

### Issue 4: VHDL Multiple Driver Error
**Problem:** Both half-adder and synchronizer tried to drive GPIO bits 2,3  
**Symptom:** "Net nios_xb_gpio_in[3] cannot be assigned more than one value"  
**Solution:** Conditional generate to skip bits 2,3 in synchronizer loop

### Issue 5: Python API Lacks GPIO Support
**Problem:** `bladerf.BladeRF()` object has no GPIO methods  
**Symptom:** `AttributeError: 'BladeRF' object has no attribute 'config_gpio_write'`  
**Solution:** Use C programs with libbladeRF instead

### Issue 6: Wrong GPIO Bank (CURRENT ISSUE)
**Problem:** Used `bladerf_config_gpio_*` but half-adder is on expansion GPIO  
**Symptom:** Writes don't reach FPGA, reads always return 0  
**Solution:** Need to use `bladerf_expansion_gpio_*` functions or NIOS backend directly  
**Status:** **DEBUGGING IN PROGRESS**

---

## 📊 Build Statistics

- **FPGA Compilation Time:** ~30-40 minutes (A9 FPGA)
- **Final .rbf Size:** 13 MB (A9), 2.6 MB (A4)
- **Quartus Warnings:** ~210 (all ignorable)
- **Quartus Errors:** 0
- **Total Development Time:** ~6 hours (including all troubleshooting)

---

## 🧪 Testing Status

| Test | Status | Notes |
|------|--------|-------|
| FPGA Build | ✅ Complete | 13 MB .rbf file generated successfully |
| FPGA Load | ✅ Working | Image loads on bladeRF2 without errors |
| GPIO Write | ❌ **FAILING** | Writes to expansion GPIO return 0 on read |
| Half-Adder Logic | ⏳ Untested | Can't test until GPIO access works |
| End-to-End | ⏳ Pending | Waiting for GPIO fix |

---

## 🔄 Git Commits

All changes tracked in repository: https://github.com/DataDragoon/version_vikram

Branch: `sfcw-default-range-offset`

Key commits:
1. Initial Verilog files and VHDL integration
2. Added Python test scripts (later removed)
3. Updated QUICKSTART.md with build process
4. Added working A9 FPGA image (13MB)
5. Replaced Python with C test programs
6. Added direct backend GPIO test

---

## 📚 References

- bladeRF HDL: https://github.com/Nuand/bladeRF
- Quartus 20.1.1: https://www.intel.com/content/www/us/en/software-kit/660904/
- bladeRF2 User Manual: https://www.nuand.com/bladeRF-doc/

---

**Last Updated:** August 13, 2026 - 19:30  
**Status:** GPIO access issue being debugged
