# Half-Adder FPGA - Quick Start Checklist

## ⚠️ IMPORTANT: You need to build the .rbf first!

The standalone half-adder .rbf you created will NOT work. You need an integrated version.

---

## Step-by-Step Process

### ☐ PART 1: Build FPGA Image (PC - One Time Setup)

#### ☐ 1.1 Clone bladeRF HDL
```bash
cd C:\Users\1109h
git clone https://github.com/Nuand/bladeRF.git
```

#### ☐ 1.2 Copy your Verilog files
- Copy `half_adder.v` to: `bladeRF\hdl\fpga\platforms\bladerf-micro\vhdl\`
- Create `half_adder_gpio.v` (wrapper - see README_HALF_ADDER.md)

#### ☐ 1.3 Modify bladeRF VHDL
- Edit `bladerf-hosted.vhd` to integrate half-adder (see README_HALF_ADDER.md)
- Edit `bladerf-hosted.qip` to add Verilog files

#### ☐ 1.4 Build in Quartus
```bash
# Open Quartus → Open Project
# bladeRF\hdl\fpga\platforms\bladerf-micro\build\bladerf.qpf
# Processing → Start Compilation (takes 20-30 min)
```

#### ☐ 1.5 Copy .rbf to your project
```bash
cp bladeRF\hdl\fpga\platforms\bladerf-micro\build\output_files\bladerf.rbf ^
   version_vikram\fpga\custom_images\half_adder_bladerf.rbf
```

---

### ☐ PART 2: Deploy to Git (PC)

```bash
cd C:\Users\1109h\version_vikram
git add fpga/custom_images/half_adder_bladerf.rbf
git add pi/test_half_adder_fpga.py
git add fpga/*.md
git commit -m "Add half-adder FPGA integration"
git push origin main
```

---

### ☐ PART 3: Test on Pi

#### ☐ 3.1 Pull latest code
```bash
ssh pi@raspberrypi.local
cd ~/version_vikram
git pull
```

#### ☐ 3.2 Run test
```bash
python3 pi/test_half_adder_fpga.py --fpga fpga/custom_images/half_adder_bladerf.rbf
```

#### ☐ 3.3 Verify output
Expected:
```
A=0, B=0 -> SUM=0, COUT=0 ✓ PASS
A=0, B=1 -> SUM=1, COUT=0 ✓ PASS
A=1, B=0 -> SUM=1, COUT=0 ✓ PASS
A=1, B=1 -> SUM=0, COUT=1 ✓ PASS
✓ All tests PASSED!
```

---

## Testing Individual Values

You can modify `test_half_adder_fpga.py` to test specific values:

```python
# Add after line: tester = HalfAdderFPGATest(...)

# Test specific values
tester.set_inputs(a=1, b=0)
sum_out, cout_out = tester.read_outputs()
print(f"A=1, B=0 -> SUM={sum_out}, COUT={cout_out}")
```

---

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| Custom .rbf | `fpga/custom_images/half_adder_bladerf.rbf` | FPGA bitstream |
| Test script | `pi/test_half_adder_fpga.py` | Python test |
| Instructions | `fpga/README_HALF_ADDER.md` | Detailed guide |
| This checklist | `fpga/QUICKSTART.md` | Quick reference |

---

## Need Help?

See `fpga/README_HALF_ADDER.md` for:
- Detailed integration steps
- VHDL code examples
- Troubleshooting guide
