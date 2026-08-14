# 16-bit Adder Test Suite

Test program for the 16-bit combinational adder implemented in the bladeRF FPGA.

## Overview

This test suite verifies the functionality of the 16-bit adder accessible via the config GPIO interface.

## Files

- `test_adder_16bit.c` - Main test program
- `Makefile` - Build configuration
- `README.md` - This file

## Building

```bash
make
```

## Running

```bash
make run
```

Or directly:
```bash
./test_adder_16bit
```

## Test Cases

The test suite includes:

1. **Basic tests** - Simple additions (0+0, 1+1, etc.)
2. **Edge cases** - Maximum values, overflow conditions
3. **Powers of 2** - Binary-friendly values
4. **Random values** - Various combinations

## Expected Output

```
===========================================
  bladeRF 16-bit Adder Test Suite
===========================================

Device opened successfully
Running 15 test cases...

Test 1: [PASS] Zero + Zero
        0 + 0 = 0 (carry=0)

Test 2: [PASS] 1 + 1
        1 + 1 = 2 (carry=0)

...

===========================================
  Test Results:
  Passed: 15/15
  Failed: 0/15
===========================================

✓ All tests passed!
```

## Requirements

- bladeRF hardware with custom FPGA image loaded
- libbladeRF installed
- GCC compiler

## Protocol

The adder uses the following GPIO mapping:

**Input (gpio_in):**
- Bits [15:0]  = Operand A (16 bits)
- Bits [31:16] = Operand B (16 bits)

**Output (gpio_out):**
- Bits [15:0]  = Sum (16 bits)
- Bit [16]     = Carry out
- Bits [31:17] = Unused (always 0)

## Notes

- The adder is **pure combinational** - no clock needed
- Results are available immediately after writing operands
- Tests include overflow cases where carry=1
