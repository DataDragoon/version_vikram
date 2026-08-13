#!/usr/bin/env python3
"""
Test script for half-adder running on bladeRF FPGA.
Requires custom FPGA image with half-adder integrated into GPIO.

GPIO Mapping:
- gpio_in[0] = A (input to FPGA)
- gpio_in[1] = B (input to FPGA)
- gpio_out[2] = SUM (output from FPGA)
- gpio_out[3] = COUT (output from FPGA)
"""

import bladerf
import time
import sys

class HalfAdderFPGATest:
    def __init__(self, fpga_image_path=None):
        """Initialize bladeRF and optionally load custom FPGA image"""
        print("Opening bladeRF device...")
        try:
            self.dev = bladerf.BladeRF()
            print(f"Device opened: {self.dev.get_serial()}")

            if fpga_image_path:
                print(f"Loading custom FPGA image: {fpga_image_path}")
                self.dev.load_fpga(fpga_image_path)
                print("FPGA image loaded successfully!")
                time.sleep(1)  # Wait for FPGA to stabilize

        except Exception as e:
            print(f"Error opening device: {e}")
            sys.exit(1)

    def set_inputs(self, a: bool, b: bool):
        """
        Set half-adder inputs A and B via GPIO.
        GPIO bits [1:0] are configured as outputs (to write to FPGA inputs).
        """
        # Set GPIO direction: bits 0,1 as output (we write to them)
        # Direction register: 1 = output, 0 = input
        direction = 0x03  # 0b00000011 - bits 0,1 are outputs
        self.dev.config_gpio_dir_write(direction)

        # Prepare value: bit 0 = A, bit 1 = B
        value = (int(b) << 1) | int(a)

        # Write to GPIO
        self.dev.config_gpio_write(value)

        # Small delay for FPGA to process
        time.sleep(0.001)

    def read_outputs(self):
        """
        Read half-adder outputs SUM and COUT from GPIO.
        GPIO bits [3:2] contain the outputs.
        """
        # Read GPIO value
        gpio_val = self.dev.config_gpio_read()

        # Extract outputs: bit 2 = SUM, bit 3 = COUT
        sum_out = (gpio_val >> 2) & 0x01
        cout_out = (gpio_val >> 3) & 0x01

        return sum_out, cout_out

    def test_half_adder(self):
        """Test all combinations of half-adder inputs"""
        print("\n" + "="*50)
        print("Testing Half-Adder on FPGA")
        print("="*50)

        # Truth table for half-adder
        expected = [
            (0, 0, 0, 0),  # A=0, B=0 -> SUM=0, COUT=0
            (0, 1, 1, 0),  # A=0, B=1 -> SUM=1, COUT=0
            (1, 0, 1, 0),  # A=1, B=0 -> SUM=1, COUT=0
            (1, 1, 0, 1),  # A=1, B=1 -> SUM=0, COUT=1
        ]

        all_passed = True

        for a, b, expected_sum, expected_cout in expected:
            # Set inputs
            self.set_inputs(a, b)

            # Read outputs
            sum_out, cout_out = self.read_outputs()

            # Check results
            passed = (sum_out == expected_sum) and (cout_out == expected_cout)
            status = "✓ PASS" if passed else "✗ FAIL"

            print(f"A={a}, B={b} -> SUM={sum_out}, COUT={cout_out} "
                  f"(expected SUM={expected_sum}, COUT={expected_cout}) {status}")

            if not passed:
                all_passed = False

        print("="*50)
        if all_passed:
            print("✓ All tests PASSED!")
        else:
            print("✗ Some tests FAILED!")
        print("="*50)

        return all_passed

    def close(self):
        """Close bladeRF device"""
        if hasattr(self, 'dev'):
            print("\nClosing device...")
            # No explicit close needed - handled by destructor

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Test half-adder on bladeRF FPGA')
    parser.add_argument('--fpga', type=str, help='Path to custom FPGA .rbf file')
    args = parser.parse_args()

    # Initialize and test
    tester = HalfAdderFPGATest(fpga_image_path=args.fpga)
    tester.test_half_adder()
    tester.close()
