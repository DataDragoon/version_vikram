#!/usr/bin/env python3
"""
Manual test script for half-adder FPGA.
Allows you to input A and B values interactively.
"""

import bladerf
import sys

def load_fpga(fpga_path=None):
    """Load FPGA image if provided"""
    dev = bladerf.BladeRF()
    print(f"Device opened: {dev.get_serial()}")

    if fpga_path:
        print(f"Loading FPGA image: {fpga_path}")
        dev.load_fpga(fpga_path)
        print("FPGA loaded successfully!\n")

    return dev

def set_inputs(dev, a, b):
    """Set GPIO inputs for half-adder"""
    direction = 0x03  # Bits 0,1 as output
    dev.config_gpio_dir_write(direction)

    value = (int(b) << 1) | int(a)
    dev.config_gpio_write(value)

def read_outputs(dev):
    """Read GPIO outputs from half-adder"""
    gpio_val = dev.config_gpio_read()
    sum_out = (gpio_val >> 2) & 0x01
    cout_out = (gpio_val >> 3) & 0x01
    return sum_out, cout_out

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Manual half-adder test')
    parser.add_argument('--fpga', type=str, help='Path to FPGA .rbf file')
    parser.add_argument('--a', type=int, choices=[0, 1], help='Input A value (0 or 1)')
    parser.add_argument('--b', type=int, choices=[0, 1], help='Input B value (0 or 1)')
    args = parser.parse_args()

    # Load device
    dev = load_fpga(args.fpga)

    if args.a is not None and args.b is not None:
        # Command-line mode
        a, b = args.a, args.b
        print(f"Testing: A={a}, B={b}")
        set_inputs(dev, a, b)
        sum_out, cout_out = read_outputs(dev)
        print(f"Result: SUM={sum_out}, COUT={cout_out}\n")

        # Show truth
        expected_sum = a ^ b
        expected_cout = a & b
        if sum_out == expected_sum and cout_out == expected_cout:
            print("✓ Correct!")
        else:
            print(f"✗ Expected: SUM={expected_sum}, COUT={expected_cout}")
    else:
        # Interactive mode
        print("="*50)
        print("Interactive Half-Adder Test")
        print("="*50)
        print("Enter values for A and B (0 or 1)")
        print("Type 'quit' or 'exit' to stop\n")

        while True:
            try:
                # Get A
                a_input = input("A = ").strip().lower()
                if a_input in ['quit', 'exit', 'q']:
                    break
                a = int(a_input)
                if a not in [0, 1]:
                    print("Error: A must be 0 or 1\n")
                    continue

                # Get B
                b_input = input("B = ").strip().lower()
                if b_input in ['quit', 'exit', 'q']:
                    break
                b = int(b_input)
                if b not in [0, 1]:
                    print("Error: B must be 0 or 1\n")
                    continue

                # Test
                set_inputs(dev, a, b)
                sum_out, cout_out = read_outputs(dev)

                # Expected
                expected_sum = a ^ b
                expected_cout = a & b

                # Display result
                status = "✓" if (sum_out == expected_sum and cout_out == expected_cout) else "✗"
                print(f"\nResult: SUM={sum_out}, COUT={cout_out} {status}")
                print(f"Expected: SUM={expected_sum}, COUT={expected_cout}\n")
                print("-"*50 + "\n")

            except ValueError:
                print("Error: Please enter 0 or 1\n")
            except KeyboardInterrupt:
                print("\n\nExiting...")
                break
            except EOFError:
                break

if __name__ == "__main__":
    main()
