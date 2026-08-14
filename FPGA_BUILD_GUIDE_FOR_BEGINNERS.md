# Complete FPGA Build Guide for Beginners

**Build your own custom logic for bladeRF FPGA and load it via USB!**

This guide walks you through adding custom Verilog logic to the bladeRF FPGA, from writing your code to loading the final `.rbf` file on the device.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Project Structure](#project-structure)
3. [Step 1: Create Your Verilog Modules](#step-1-create-your-verilog-modules)
4. [Step 2: Register Files in Quartus Project](#step-2-register-files-in-quartus-project)
5. [Step 3: Integrate into VHDL Top-Level](#step-3-integrate-into-vhdl-top-level)
6. [Step 4: Build FPGA Image](#step-4-build-fpga-image)
7. [Step 5: Load and Test](#step-5-load-and-test)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

1. **Intel Quartus Prime 20.1.1 Lite Edition**
   - Download: [Intel Quartus 20.1.1](https://www.intel.com/content/www/us/en/software-kit/660904/)
   - **⚠️ Must be version 20.1.1** (newer versions don't support NIOS II)
   - Install these components:
     - ✅ Quartus Prime
     - ✅ Cyclone V device support
     - ✅ NIOS II EDS

2. **Git Bash** (Windows) or **Bash** (Linux)
   - Download: [Git for Windows](https://git-scm.com/download/win)

3. **bladeRF Repository**
   ```bash
   cd ~
   git clone https://github.com/Nuand/bladeRF.git
   ```

### Check Your bladeRF Device

Connect your bladeRF and check the FPGA size:

```bash
bladeRF-cli -e "info"
```

Look for the line: `FPGA size: XXX KLE`
- **49 KLE** → A4 size
- **115 KLE** → A5 size  
- **301 KLE** → A9 size ← Most common for bladeRF2 Micro

**Remember your FPGA size!** You'll need it for the build command.

---

## Project Structure

```
bladeRF/
└── hdl/
    └── fpga/
        └── platforms/
            └── bladerf-micro/
                ├── vhdl/                    ← PUT YOUR .v FILES HERE
                │   ├── your_logic.v         ← Your core logic
                │   └── your_logic_gpio.v    ← GPIO wrapper
                ├── bladerf-hosted.qip       ← Register files here
                └── vhdl/
                    └── bladerf-hosted.vhd   ← Integrate here
```

---

## Step 1: Create Your Verilog Modules

### 1.1 Create Your Core Logic

**File:** `~/bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/your_logic.v`

```verilog
// Example: 16-bit adder
// Replace this with YOUR custom logic!

module your_logic(
    input [15:0] a,        // First input
    input [15:0] b,        // Second input
    output [15:0] sum,     // Output sum
    output cout            // Carry out
);

    // Your logic here
    assign {cout, sum} = a + b;

endmodule
```

**Tips:**
- Keep it **combinational** if possible (no clock = simpler!)
- If you need a clock, add `input clk`
- Test your logic separately before FPGA integration

---

### 1.2 Create GPIO Wrapper

**File:** `~/bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/your_logic_gpio.v`

```verilog
// GPIO wrapper - connects your logic to bladeRF's 32-bit GPIO bus
// This is how the PC communicates with your FPGA logic via USB

module your_logic_gpio(
    input wire [31:0] gpio_in,     // Data from PC (via USB)
    output wire [31:0] gpio_out    // Data to PC (via USB)
);

    // Extract inputs from GPIO (customize bit mapping!)
    wire [15:0] operand_a = gpio_in[15:0];   // Lower 16 bits = A
    wire [15:0] operand_b = gpio_in[31:16];  // Upper 16 bits = B
    
    // Your module outputs
    wire [15:0] sum;
    wire cout;
    
    // Instantiate your core logic
    your_logic core_inst (
        .a(operand_a),
        .b(operand_b),
        .sum(sum),
        .cout(cout)
    );
    
    // Pack outputs to GPIO (customize bit mapping!)
    // gpio_out[15:0]  = sum (16 bits)
    // gpio_out[16]    = carry out (1 bit)
    // gpio_out[31:17] = unused (set to 0)
    assign gpio_out = {15'b0, cout, sum};

endmodule
```

**GPIO Bit Mapping:**

| Direction | Bits | Purpose | Your Data |
|-----------|------|---------|-----------|
| **Input** (from PC) | `[15:0]` | First operand | `operand_a` |
| **Input** (from PC) | `[31:16]` | Second operand | `operand_b` |
| **Output** (to PC) | `[15:0]` | Result | `sum` |
| **Output** (to PC) | `[16]` | Carry | `cout` |
| **Output** (to PC) | `[31:17]` | Unused | `0` |

**Customize this for your logic!**

---

## Step 2: Register Files in Quartus Project

Edit: `~/bladeRF/hdl/fpga/platforms/bladerf-micro/bladerf-hosted.qip`

**Open the file:**
```bash
cd ~/bladeRF/hdl/fpga/platforms/bladerf-micro
nano bladerf-hosted.qip
# or use your favorite text editor
```

**Scroll to the end** and add these lines:

```tcl
set_global_assignment -name VERILOG_FILE [file normalize [file join $here vhdl/your_logic.v]]
set_global_assignment -name VERILOG_FILE [file normalize [file join $here vhdl/your_logic_gpio.v]]
```

**Replace `your_logic` with your actual module names!**

**Save and close** the file.

---

## Step 3: Integrate into VHDL Top-Level

Edit: `~/bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/bladerf-hosted.vhd`

This file integrates your Verilog modules into the bladeRF FPGA design.

### 3.1 Declare Component

**Find line ~185** (search for `begin` keyword and add BEFORE it):

```vhdl
    -- ============================================
    -- Your custom logic component declaration
    -- ============================================
    component your_logic_gpio
        port (
            gpio_in  : in  std_logic_vector(31 downto 0);
            gpio_out : out std_logic_vector(31 downto 0)
        );
    end component;

    signal your_logic_output : std_logic_vector(31 downto 0);
```

**Replace `your_logic` with your actual module name!**

---

### 3.2 Connect to NIOS GPIO

**Find line ~393** (search for `gpio_in_port`):

**Change:**
```vhdl
gpio_in_port => pack(nios_gpio.i, '0'),
```

**To:**
```vhdl
gpio_in_port => your_logic_output,  -- PC reads your FPGA output here
```

**Keep:**
```vhdl
gpio_out_port => nios_gpo_slv,      -- PC writes to FPGA here
```

---

### 3.3 Instantiate Your Module

**Find line ~988** (search for `generate_sync_xb_gpio_in`):

**Add BEFORE that section:**

```vhdl
    -- ============================================
    -- Your Custom Logic Instantiation
    -- ============================================
    U_your_logic : your_logic_gpio
        port map (
            gpio_in  => nios_gpo_slv,        -- Input from PC
            gpio_out => your_logic_output    -- Output to PC
        );
```

**Replace `your_logic` with your actual module name!**

**Save and close** the file.

---

## Step 4: Build FPGA Image

### 4.1 Setup Environment

Open Git Bash (Windows) or Terminal (Linux):

```bash
cd ~/bladeRF/hdl/quartus

# Setup Quartus environment
export QUARTUS_ROOTDIR="/c/intelFPGA_lite/20.1/quartus"
export QUARTUS_BINDIR="/c/intelFPGA_lite/20.1/quartus/bin64"
export SOPC_KIT_NIOS2="/c/intelFPGA_lite/20.1/nios2eds"

# Add tools to PATH
export PATH="/c/intelFPGA_lite/20.1/quartus/bin64:$PATH"
export PATH="/c/intelFPGA_lite/20.1/quartus/sopc_builder/bin:$PATH"
export PATH="/c/intelFPGA_lite/20.1/nios2eds/sdk2/bin:$PATH"
export PATH="/c/intelFPGA_lite/20.1/nios2eds/bin/gnu/H-x86_64-mingw32/bin:$PATH"

# Verify tools are found
which quartus_sh
quartus_sh --version | head -3
```

**Linux users:** Change `/c/` to your actual installation path (e.g., `/opt/` or `~/`)

**Expected output:**
```
/c/intelFPGA_lite/20.1/quartus/bin64/quartus_sh
Quartus Prime Shell
Version 20.1.1 Build 720 11/11/2020 SJ Lite Edition
```

---

### 4.2 Run Build Script

**Fix line endings** (Windows Git Bash only):
```bash
sed -i 's/\r$//' build_bladerf.sh
```

**Start the build** (replace `A9` with your FPGA size from Prerequisites):

```bash
./build_bladerf.sh -b bladeRF-micro -s A9 -r hosted
```

**FPGA size options:**
- `-s A4` → 49 KLE
- `-s A9` → 301 KLE (most common)
- `-s 115` → Same as A9

---

### 4.3 Build Process

The script will:

1. **Generate NIOS system** (~2 min)
2. **Build BSP** (~3 min)  
   **⚠️ If BSP fails with "No rule to make target" error:**
   
   ```bash
   # Fix the BSP Makefile
   cd work/bladerf-micro-A9-hosted/bladeRF_nios_bsp
   
   # Replace line 65
   sed -i 's|ABS_BSP_ROOT := $(shell pwd)|ABS_BSP_ROOT := C:/Users/YOUR_USERNAME/bladeRF/hdl/quartus/work/bladerf-micro-A9-hosted/bladeRF_nios_bsp|' Makefile
   
   # Build BSP manually
   make
   
   # Continue with mem_init generation (next step)
   ```

3. **Generate memory files** (~2 min)
   
   If build stops after BSP, run manually:
   ```bash
   cd ../../fpga/platforms/bladerf-micro/software/bladeRF_nios
   make WORKDIR=work/bladerf-micro-A9-hosted mem_init_generate
   ```

4. **Quartus compilation** (~30-50 minutes!)
   - Analysis & Synthesis (~10-15 min)
   - Fitter (~15-25 min)
   - Timing Analysis (~2-5 min)
   - Assembler (~2-5 min)

**Grab some coffee! ☕ This takes 30-50 minutes total.**

---

### 4.4 Monitor Progress

Open another terminal and watch the build:

```bash
cd ~/bladeRF/hdl/quartus
tail -f work/bladerf-micro-A9-hosted/output_files/*.rpt
```

Or check for errors:
```bash
grep -i error work/bladerf-micro-A9-hosted/output_files/*.rpt
```

---

### 4.5 Verify Output

**Check if .rbf file was generated:**

```bash
ls -lh work/bladerf-micro-A9-hosted/output_files/*.rbf
```

**Expected output:**
```
-rw-r--r-- 1 user user 13M Aug 14 15:30 hosted.rbf
```

**File size check:**
- **A4 (49 KLE):** ~2.6 MB
- **A9 (301 KLE):** ~13 MB

If file size is much smaller, the memory initialization files are missing! Go back to step 4.3 and run `mem_init_generate` manually.

---

## Step 5: Load and Test

### 5.1 Copy FPGA Image

```bash
# Copy to your project directory (optional)
cp work/bladerf-micro-A9-hosted/output_files/hosted.rbf \
   ~/version_vikram/fpga/custom_images/my_custom_logic.rbf
```

---

### 5.2 Load to bladeRF

**Temporary load** (lost on power cycle):
```bash
bladeRF-cli -l work/bladerf-micro-A9-hosted/output_files/hosted.rbf
```

**Permanent flash** (survives power cycle):
```bash
bladeRF-cli -f work/bladerf-micro-A9-hosted/output_files/hosted.rbf
```

**Expected output:**
```
Configuring FPGA...
  Done! FPGA configured successfully.
```

---

### 5.3 Write Test Program

**File:** `test_my_logic.c`

```c
#include <stdio.h>
#include <stdint.h>
#include <libbladeRF.h>

int main() {
    struct bladerf *dev;
    uint32_t input_val, output_val;
    int status;
    
    // Open device
    status = bladerf_open(&dev, NULL);
    if (status != 0) {
        fprintf(stderr, "Failed to open bladeRF: %s\n", 
                bladerf_strerror(status));
        return 1;
    }
    
    // Example: Send two 16-bit numbers (100 and 200)
    uint16_t a = 100;
    uint16_t b = 200;
    
    // Pack into 32-bit value (match your GPIO mapping!)
    input_val = ((uint32_t)b << 16) | a;
    
    printf("Testing custom logic...\n");
    printf("Input A: %u\n", a);
    printf("Input B: %u\n", b);
    
    // Write to FPGA
    status = bladerf_config_gpio_write(dev, input_val);
    if (status != 0) {
        fprintf(stderr, "GPIO write failed: %s\n", 
                bladerf_strerror(status));
        bladerf_close(dev);
        return 1;
    }
    
    // Read result from FPGA
    status = bladerf_config_gpio_read(dev, &output_val);
    if (status != 0) {
        fprintf(stderr, "GPIO read failed: %s\n", 
                bladerf_strerror(status));
        bladerf_close(dev);
        return 1;
    }
    
    // Extract results (match your GPIO mapping!)
    uint16_t sum = output_val & 0xFFFF;
    uint8_t carry = (output_val >> 16) & 0x1;
    
    printf("\nResult:\n");
    printf("Sum: %u\n", sum);
    printf("Carry: %u\n", carry);
    printf("Expected: %u + %u = %u (carry=%u)\n", 
           a, b, a+b, ((a+b) > 65535 ? 1 : 0));
    
    // Cleanup
    bladerf_close(dev);
    return 0;
}
```

**Compile and run:**

```bash
gcc -o test_my_logic test_my_logic.c -lbladeRF
./test_my_logic
```

**Expected output:**
```
Testing custom logic...
Input A: 100
Input B: 200

Result:
Sum: 300
Carry: 0
Expected: 100 + 200 = 300 (carry=0)
```

---

## Troubleshooting

### Build Errors

#### Error: "quartus_sh: command not found"

**Solution:** Environment variables not set. Run setup commands from Step 4.1

---

#### Error: "No rule to make target system.h"

**Problem:** BSP Makefile has MSYS path issues

**Solution:**
```bash
cd ~/bladeRF/hdl/quartus/work/bladerf-micro-A9-hosted/bladeRF_nios_bsp

# Fix Makefile line 65
sed -i 's|ABS_BSP_ROOT := $(shell pwd)|ABS_BSP_ROOT := C:/Users/YOUR_USERNAME/bladeRF/hdl/quartus/work/bladerf-micro-A9-hosted/bladeRF_nios_bsp|' Makefile

# Build manually
make
```

---

#### Error: "File not found: your_logic.v"

**Problem:** File not in correct directory or wrong path in `.qip`

**Solution:**
```bash
# Check files exist
ls ~/bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/*.v

# Verify .qip file
grep "your_logic" ~/bladeRF/hdl/fpga/platforms/bladerf-micro/bladerf-hosted.qip
```

---

#### Error: "Net nios_xb_gpio_in cannot be assigned more than one value"

**Problem:** Multiple modules driving the same GPIO signal

**Solution:** Only connect **one** module to `gpio_in_port`. Check your modifications in `bladerf-hosted.vhd` line ~393.

---

### Runtime Errors

#### Error: "Failed to open bladeRF device"

**Problem:** Device not connected or USB permissions

**Solution:**
```bash
# Check device is connected
bladeRF-cli -e "info"

# Linux: Check USB permissions
sudo bladeRF-cli -e "info"
```

---

#### Wrong Results from FPGA

**Problem:** GPIO bit mapping mismatch

**Solution:**
1. Double-check bit positions in `your_logic_gpio.v`
2. Match bit extraction in your test program
3. Add debug prints:

```c
printf("Raw GPIO write: 0x%08X\n", input_val);
printf("Raw GPIO read:  0x%08X\n", output_val);
```

---

#### Build Succeeds but .rbf File is Too Small

**Problem:** Memory initialization files missing

**Solution:**
```bash
cd ~/bladeRF/hdl/fpga/platforms/bladerf-micro/software/bladeRF_nios
make WORKDIR=work/bladerf-micro-A9-hosted mem_init_generate

# Verify files exist
ls -lh ../../quartus/work/bladerf-micro-A9-hosted/bladeRF_nios/mem_init/
```

Expected files:
- `meminit.qip`
- `meminit.spd`
- `nios_system_ram.hex` (~670 KB)

Then rebuild Quartus project.

---

## Quick Reference

### File Locations

| File | Location |
|------|----------|
| Your core logic | `bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/your_logic.v` |
| GPIO wrapper | `bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/your_logic_gpio.v` |
| Quartus project | `bladeRF/hdl/fpga/platforms/bladerf-micro/bladerf-hosted.qip` |
| VHDL top-level | `bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/bladerf-hosted.vhd` |
| Build script | `bladeRF/hdl/quartus/build_bladerf.sh` |
| Output .rbf | `bladeRF/hdl/quartus/work/bladerf-micro-A9-hosted/output_files/hosted.rbf` |

---

### Build Commands (Complete)

```bash
# 1. Setup environment
cd ~/bladeRF/hdl/quartus
export QUARTUS_ROOTDIR="/c/intelFPGA_lite/20.1/quartus"
export QUARTUS_BINDIR="/c/intelFPGA_lite/20.1/quartus/bin64"
export SOPC_KIT_NIOS2="/c/intelFPGA_lite/20.1/nios2eds"
export PATH="/c/intelFPGA_lite/20.1/quartus/bin64:$PATH"
export PATH="/c/intelFPGA_lite/20.1/quartus/sopc_builder/bin:$PATH"
export PATH="/c/intelFPGA_lite/20.1/nios2eds/sdk2/bin:$PATH"
export PATH="/c/intelFPGA_lite/20.1/nios2eds/bin/gnu/H-x86_64-mingw32/bin:$PATH"

# 2. Build FPGA image (replace A9 with your FPGA size)
./build_bladerf.sh -b bladeRF-micro -s A9 -r hosted

# 3. If BSP fails, fix and build manually
cd work/bladerf-micro-A9-hosted/bladeRF_nios_bsp
sed -i 's|ABS_BSP_ROOT := $(shell pwd)|ABS_BSP_ROOT := C:/Users/YOUR_USERNAME/bladeRF/hdl/quartus/work/bladerf-micro-A9-hosted/bladeRF_nios_bsp|' Makefile
make
cd ../../fpga/platforms/bladerf-micro/software/bladeRF_nios
make WORKDIR=work/bladerf-micro-A9-hosted mem_init_generate

# 4. Continue Quartus build manually if needed
cd ../../../../quartus/work/bladerf-micro-A9-hosted
quartus_sh --64bit -t ../../build.tcl -projname bladerf -rev hosted -flow full

# 5. Find output
ls -lh output_files/hosted.rbf
```

---

### Test Commands

```bash
# Load FPGA temporarily
bladeRF-cli -l hosted.rbf

# Compile test program
gcc -o test test.c -lbladeRF

# Run test
./test
```

---

## Example: Working 16-bit Adder

This repository includes a working example of a 16-bit adder:

**Files:**
- `bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/adder_16bit.v`
- `bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/adder_16bit_gpio.v`
- Integration already done in `bladerf-hosted.vhd`

**Test program:**
- `version_vikram/test_adder_16bit.c`

Study these files as a reference for your own custom logic!

---

## Tips for Success

1. **Start simple** - Test with a basic module first (e.g., bit inversion, simple adder)
2. **Document your GPIO mapping** - Write comments in your code showing which bits do what
3. **Test incrementally** - Don't add complex logic all at once
4. **Save working versions** - Git commit after each successful build
5. **Check timing** - Look for timing violations in `*.sta.rpt` files
6. **Monitor resources** - Check FPGA utilization doesn't exceed 95%

---

## Next Steps

Once you have your basic logic working:

1. Add more complex algorithms
2. Integrate with RF frontend (TX/RX streams)
3. Use multiple GPIO signals
4. Add internal registers for configuration
5. Implement state machines

---

## Resources

- **bladeRF Documentation:** https://github.com/Nuand/bladeRF/wiki
- **Quartus Documentation:** Included in installation at `intelFPGA_lite/20.1/quartus/doc/`
- **NIOS II Documentation:** Included in installation at `intelFPGA_lite/20.1/nios2eds/`
- **libbladeRF API:** https://www.nuand.com/libbladeRF-doc/

---

## Success! 🎉

You now know how to:
- ✅ Write custom Verilog logic for bladeRF
- ✅ Integrate it into the FPGA design
- ✅ Build the FPGA image from source
- ✅ Load and test on real hardware

**Happy FPGA hacking!** 🚀

---

**Last Updated:** August 14, 2026  
**Tested On:** bladeRF2 Micro (A9), Windows 11, Quartus 20.1.1
