# Half-Adder FPGA Integration Guide

## ⚠️ CRITICAL INFORMATION

You **CANNOT** load a standalone half-adder .rbf file directly. The .rbf must include:
1. Full bladeRF functionality (USB controller, RF interface)
2. Your half-adder logic integrated into the GPIO interface

## Complete Workflow

### PHASE 1: Build Custom FPGA Image (PC with Quartus)

#### Step 1: Clone bladeRF HDL Repository

```bash
# On PC (Windows)
cd C:\Users\1109h
git clone https://github.com/Nuand/bladeRF.git
cd bladeRF
```

#### Step 2: Add Your Verilog Files

Copy these files to: `C:\Users\1109h\bladeRF\hdl\fpga\platforms\bladerf-micro\vhdl\`

**File 1: `half_adder.v`** (your existing file)
```verilog
module half_adder(
    input a,
    input b,
    output sum,
    output cout
);
    assign sum = a^b;
    assign cout = a&b;
endmodule
```

**File 2: `half_adder_gpio.v`** (new wrapper)
```verilog
// Half-adder GPIO wrapper
// GPIO[1:0] = inputs (A, B)  
// GPIO[3:2] = outputs (SUM, COUT)

module half_adder_gpio(
    input wire [31:0] gpio_in,
    output wire [31:0] gpio_out
);
    wire a = gpio_in[0];
    wire b = gpio_in[1];
    wire sum, cout;

    half_adder adder_inst (
        .a(a),
        .b(b),
        .sum(sum),
        .cout(cout)
    );

    assign gpio_out = {28'b0, cout, sum, 2'b0};
endmodule
```

#### Step 3: Modify bladeRF VHDL Top-Level

Edit: `C:\Users\1109h\bladeRF\hdl\fpga\platforms\bladerf-micro\vhdl\bladerf-hosted.vhd`

Find the line around line 542:
```vhdl
generate_xb_gpio_out : for i in exp_gpio'range generate
    exp_gpio(i) <= nios_xb_gpio_out(i) when nios_xb_gpio_oe(i) = '1' else 'Z';
```

**ADD BEFORE IT:**
```vhdl
-- Half-adder integration
component half_adder_gpio
    port (
        gpio_in  : in  std_logic_vector(31 downto 0);
        gpio_out : out std_logic_vector(31 downto 0)
    );
end component;

signal half_adder_out : std_logic_vector(31 downto 0);

-- Instantiate half-adder
U_half_adder : half_adder_gpio
    port map (
        gpio_in  => nios_xb_gpio_out,
        gpio_out => half_adder_out
    );

-- Override GPIO inputs with half-adder outputs (bits 3:2)
nios_xb_gpio_in(3 downto 2) <= half_adder_out(3 downto 2);
```

#### Step 4: Add Files to Quartus Project

Edit: `C:\Users\1109h\bladeRF\hdl\fpga\platforms\bladerf-micro\bladerf-hosted.qip`

Add these lines at the end:
```tcl
set_global_assignment -name VERILOG_FILE vhdl/half_adder.v
set_global_assignment -name VERILOG_FILE vhdl/half_adder_gpio.v
```

#### Step 5: Build FPGA Image

**Option A: Use Build Script (Linux/WSL)**
```bash
cd C:\Users\1109h\bladeRF\hdl\fpga\platforms\bladerf-micro
./build_bladerf.sh --app hosted
```

**Option B: Manual Quartus Build (Windows)**
1. Open Quartus
2. Open project: `C:\Users\1109h\bladeRF\hdl\fpga\platforms\bladerf-micro\build\bladerf.qpf`
3. Processing → Start Compilation
4. Wait ~20-30 minutes
5. Output will be in: `build/output_files/bladerf.rbf`

#### Step 6: Copy .rbf to Your Project

```bash
cp build/output_files/bladerf.rbf C:\Users\1109h\version_vikram\fpga\custom_images\half_adder_bladerf.rbf
```

---

### PHASE 2: Push to Git and Deploy to Pi

#### Step 1: Commit and Push (PC)

```bash
cd C:\Users\1109h\version_vikram
git add fpga/custom_images/half_adder_bladerf.rbf
git add pi/test_half_adder_fpga.py
git commit -m "Add half-adder FPGA image and test script"
git push origin main
```

#### Step 2: Pull on Raspberry Pi

```bash
# SSH into Pi
ssh pi@raspberrypi.local

# Navigate to project
cd ~/version_vikram
git pull origin main
```

---

### PHASE 3: Test on Raspberry Pi

#### Step 1: Load FPGA Image

```bash
cd ~/version_vikram
python3 pi/test_half_adder_fpga.py --fpga fpga/custom_images/half_adder_bladerf.rbf
```

#### Expected Output:

```
Opening bladeRF device...
Device opened: <serial>
Loading custom FPGA image: fpga/custom_images/half_adder_bladerf.rbf
FPGA image loaded successfully!

==================================================
Testing Half-Adder on FPGA
==================================================
A=0, B=0 -> SUM=0, COUT=0 (expected SUM=0, COUT=0) ✓ PASS
A=0, B=1 -> SUM=1, COUT=0 (expected SUM=1, COUT=0) ✓ PASS
A=1, B=0 -> SUM=1, COUT=0 (expected SUM=1, COUT=0) ✓ PASS
A=1, B=1 -> SUM=0, COUT=1 (expected SUM=0, COUT=1) ✓ PASS
==================================================
✓ All tests PASSED!
==================================================
```

---

## Troubleshooting

### "Failed to open bladeRF device"
- Check USB connection
- Run: `lsusb | grep Nuand`
- Ensure bladerf library installed: `sudo apt-get install libbladerf2`

### "FPGA load failed"
- Check .rbf file path
- Ensure .rbf is the integrated version (not standalone)
- File size should be ~1-2 MB (standalone would be <1 KB)

### "All tests FAIL"
- FPGA image might not have half-adder integrated properly
- Check Quartus build logs for errors
- Verify GPIO mapping in VHDL code

### "Device disconnects after loading FPGA"
- ⚠️ You loaded a standalone .rbf (NOT integrated)
- This bricks USB until you reload factory image
- Recover: Use JTAG programmer to reload factory FPGA

---

## File Structure

```
version_vikram/
├── fpga/
│   ├── custom_images/
│   │   └── half_adder_bladerf.rbf     ← Custom FPGA image
│   └── README_HALF_ADDER.md           ← This file
└── pi/
    └── test_half_adder_fpga.py        ← Test script
```

## Quick Reference

**Load FPGA (temporary):**
```bash
python3 pi/test_half_adder_fpga.py --fpga fpga/custom_images/half_adder_bladerf.rbf
```

**Flash to persistent storage:**
```bash
bladeRF-cli -L fpga/custom_images/half_adder_bladerf.rbf
```

**Restore factory FPGA:**
```bash
bladeRF-cli -L /usr/share/Nuand/bladeRF/hostedxA4.rbf
```
