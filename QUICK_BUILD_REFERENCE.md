# Quick Build Reference Card

**Fast commands for building custom FPGA logic for bladeRF**

For complete details, see [FPGA_BUILD_GUIDE_FOR_BEGINNERS.md](FPGA_BUILD_GUIDE_FOR_BEGINNERS.md)

---

## 📁 File Locations

```
bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/
├── your_core.v              ← Your logic here
└── your_core_gpio.v         ← GPIO wrapper here

bladeRF/hdl/fpga/platforms/bladerf-micro/
└── bladerf-hosted.qip       ← Register files here (Step 1)

bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/
└── bladerf-hosted.vhd       ← Integrate here (Step 2)
```

---

## 🔧 Step 1: Register Verilog Files

Edit: `bladerf-hosted.qip`

```tcl
# Add at the end:
set_global_assignment -name VERILOG_FILE [file normalize [file join $here vhdl/your_core.v]]
set_global_assignment -name VERILOG_FILE [file normalize [file join $here vhdl/your_core_gpio.v]]
```

---

## 🔧 Step 2: Integrate in VHDL

Edit: `bladerf-hosted.vhd`

### 2a. Declare component (~line 185, before `begin`)

```vhdl
component your_core_gpio
    port (
        gpio_in  : in  std_logic_vector(31 downto 0);
        gpio_out : out std_logic_vector(31 downto 0)
    );
end component;

signal your_core_output : std_logic_vector(31 downto 0);
```

### 2b. Connect to NIOS (~line 393)

```vhdl
gpio_in_port  => your_core_output,    -- PC reads from here
gpio_out_port => nios_gpo_slv,        -- PC writes to here
```

### 2c. Instantiate (~line 988)

```vhdl
U_your_core : your_core_gpio
    port map (
        gpio_in  => nios_gpo_slv,
        gpio_out => your_core_output
    );
```

---

## 🚀 Build Commands

```bash
# Navigate to build directory
cd ~/bladeRF/hdl/quartus

# Setup environment (REQUIRED!)
export QUARTUS_ROOTDIR="/c/intelFPGA_lite/20.1/quartus"
export QUARTUS_BINDIR="/c/intelFPGA_lite/20.1/quartus/bin64"
export SOPC_KIT_NIOS2="/c/intelFPGA_lite/20.1/nios2eds"
export PATH="/c/intelFPGA_lite/20.1/quartus/bin64:$PATH"
export PATH="/c/intelFPGA_lite/20.1/quartus/sopc_builder/bin:$PATH"
export PATH="/c/intelFPGA_lite/20.1/nios2eds/sdk2/bin:$PATH"
export PATH="/c/intelFPGA_lite/20.1/nios2eds/bin/gnu/H-x86_64-mingw32/bin:$PATH"

# Fix line endings (Windows only)
sed -i 's/\r$//' build_bladerf.sh

# Build (replace A9 with your FPGA size: A4, A9, or 115)
./build_bladerf.sh -b bladeRF-micro -s A9 -r hosted
```

**Time:** 30-60 minutes ☕

**Output:** `work/bladerf-micro-A9-hosted/output_files/hosted.rbf`

---

## 🐛 Common Fix: BSP Makefile Error

If you see: `make: *** No rule to make target`

```bash
cd work/bladerf-micro-A9-hosted/bladeRF_nios_bsp

# Fix Makefile (update YOUR_USERNAME!)
sed -i 's|ABS_BSP_ROOT := $(shell pwd)|ABS_BSP_ROOT := C:/Users/YOUR_USERNAME/bladeRF/hdl/quartus/work/bladerf-micro-A9-hosted/bladeRF_nios_bsp|' Makefile

# Build BSP
make

# Generate memory files
cd ../../fpga/platforms/bladerf-micro/software/bladeRF_nios
make WORKDIR=work/bladerf-micro-A9-hosted mem_init_generate

# Continue Quartus build
cd ../../../../quartus/work/bladerf-micro-A9-hosted
quartus_sh --64bit -t ../../build.tcl -projname bladerf -rev hosted -flow full
```

---

## 📤 Load to Device

```bash
# Temporary (lost on power cycle)
bladeRF-cli -l hosted.rbf

# Permanent (flash to device)
bladeRF-cli -f hosted.rbf
```

---

## 🧪 Test Program Template

```c
#include <stdio.h>
#include <stdint.h>
#include <libbladeRF.h>

int main() {
    struct bladerf *dev;
    uint32_t input, output;
    
    bladerf_open(&dev, NULL);
    
    input = 0x12345678;  // Your data
    bladerf_config_gpio_write(dev, input);
    bladerf_config_gpio_read(dev, &output);
    
    printf("Input:  0x%08X\n", input);
    printf("Output: 0x%08X\n", output);
    
    bladerf_close(dev);
    return 0;
}
```

**Compile:**
```bash
gcc -o test test.c -lbladeRF
./test
```

---

## 📋 Verification Checklist

Before building:
- [ ] `.v` files in correct directory
- [ ] Files added to `.qip`
- [ ] Component declared in `.vhd`
- [ ] Module instantiated in `.vhd`
- [ ] Connected to NIOS GPIO

After building:
- [ ] `.rbf` file exists
- [ ] File size correct (~13 MB for A9)
- [ ] No errors in `output_files/*.rpt`

---

## 🎯 GPIO Mapping Template

**Document your bit allocation!**

```
Write (PC → FPGA):
  gpio_in[7:0]    = Command
  gpio_in[15:8]   = Parameter A
  gpio_in[23:16]  = Parameter B
  gpio_in[31:24]  = Reserved

Read (FPGA → PC):
  gpio_out[15:0]  = Result
  gpio_out[16]    = Status flag
  gpio_out[31:17] = Unused
```

---

## 🔍 Debug Commands

```bash
# Check FPGA size
bladeRF-cli -e "info"

# Verify tools
which quartus_sh
quartus_sh --version

# Monitor build
tail -f work/bladerf-micro-A9-hosted/output_files/*.rpt

# Check errors
grep -i error work/bladerf-micro-A9-hosted/output_files/*.rpt

# Check timing
grep -A10 "Timing Analyzer" work/bladerf-micro-A9-hosted/output_files/*.sta.rpt
```

---

## 📊 Expected File Sizes

| FPGA Size | .rbf Size | Build Time |
|-----------|-----------|------------|
| A4 (49 KLE) | ~2.6 MB | 20-30 min |
| A9 (301 KLE) | ~13 MB | 30-50 min |

---

## 🎓 Example: See Working Implementation

Study the 16-bit adder example:
- `bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/adder_16bit.v`
- `bladeRF/hdl/fpga/platforms/bladerf-micro/vhdl/adder_16bit_gpio.v`
- `version_vikram/test_adder_16bit.c`

---

## 💡 Pro Tips

1. **Test incrementally** - Start with simple logic
2. **Save working builds** - Git commit after success
3. **Document GPIO bits** - Comment your code!
4. **Check resources** - Keep utilization < 95%
5. **Verify timing** - Must meet 38.4 MHz constraint

---

**Complete guide:** [FPGA_BUILD_GUIDE_FOR_BEGINNERS.md](FPGA_BUILD_GUIDE_FOR_BEGINNERS.md)
