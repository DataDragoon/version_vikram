/*
 * Interactive GPIO tester for bladeRF - manual control
 * Compile: gcc test_gpio_interactive.c -o test_gpio_interactive -lbladeRF
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
#include <libbladeRF.h>

void print_gpio_bits(uint32_t val) {
    printf("GPIO Value: 0x%08X = 0b", val);
    for (int i = 31; i >= 0; i--) {
        printf("%d", (val >> i) & 1);
        if (i % 8 == 0) printf(" ");
    }
    printf("\n");
    printf("  Bit [3:0] = 0x%X\n", val & 0xF);
    printf("    Bit 0 (A)    = %d\n", (val >> 0) & 1);
    printf("    Bit 1 (B)    = %d\n", (val >> 1) & 1);
    printf("    Bit 2 (SUM)  = %d\n", (val >> 2) & 1);
    printf("    Bit 3 (COUT) = %d\n", (val >> 3) & 1);
}

int main(int argc, char *argv[]) {
    struct bladerf *dev = NULL;
    int status;

    // Open device
    printf("Opening bladeRF device...\n");
    status = bladerf_open(&dev, NULL);
    if (status != 0) {
        fprintf(stderr, "Failed to open device: %s\n", bladerf_strerror(status));
        return 1;
    }

    // Load FPGA image if provided
    if (argc > 1) {
        printf("Loading FPGA image: %s\n", argv[1]);
        status = bladerf_load_fpga(dev, argv[1]);
        if (status != 0) {
            fprintf(stderr, "Failed to load FPGA: %s\n", bladerf_strerror(status));
            bladerf_close(dev);
            return 1;
        }
        printf("FPGA loaded successfully!\n");
        sleep(1);
    }

    printf("\n");
    printf("==================================================\n");
    printf("Interactive GPIO Test\n");
    printf("==================================================\n");
    printf("Commands:\n");
    printf("  r          - Read GPIO\n");
    printf("  w <hex>    - Write GPIO value (e.g., w 0x03)\n");
    printf("  t <a> <b>  - Test half-adder with A,B (e.g., t 1 1)\n");
    printf("  q          - Quit\n");
    printf("==================================================\n\n");

    char cmd[256];
    while (1) {
        printf("> ");
        fflush(stdout);

        if (fgets(cmd, sizeof(cmd), stdin) == NULL) {
            break;
        }

        if (cmd[0] == 'q' || cmd[0] == 'Q') {
            break;
        }
        else if (cmd[0] == 'r' || cmd[0] == 'R') {
            uint32_t val;
            status = bladerf_config_gpio_read(dev, &val);
            if (status != 0) {
                fprintf(stderr, "Failed to read GPIO: %s\n", bladerf_strerror(status));
            } else {
                print_gpio_bits(val);
            }
        }
        else if (cmd[0] == 'w' || cmd[0] == 'W') {
            uint32_t val;
            if (sscanf(cmd + 1, "%x", &val) == 1) {
                printf("Writing 0x%08X to GPIO...\n", val);
                status = bladerf_config_gpio_write(dev, val);
                if (status != 0) {
                    fprintf(stderr, "Failed to write GPIO: %s\n", bladerf_strerror(status));
                } else {
                    printf("Write successful!\n");
                    usleep(10000);  // 10ms delay

                    // Read back
                    uint32_t read_val;
                    status = bladerf_config_gpio_read(dev, &read_val);
                    if (status == 0) {
                        printf("\nRead back:\n");
                        print_gpio_bits(read_val);
                    }
                }
            } else {
                printf("Invalid format. Use: w <hex_value>\n");
            }
        }
        else if (cmd[0] == 't' || cmd[0] == 'T') {
            int a, b;
            if (sscanf(cmd + 1, "%d %d", &a, &b) == 2) {
                uint32_t write_val = (b << 1) | a;
                printf("Testing A=%d, B=%d (writing 0x%X)...\n", a, b, write_val);

                status = bladerf_config_gpio_write(dev, write_val);
                if (status != 0) {
                    fprintf(stderr, "Failed to write GPIO: %s\n", bladerf_strerror(status));
                    continue;
                }

                usleep(10000);  // 10ms delay

                uint32_t read_val;
                status = bladerf_config_gpio_read(dev, &read_val);
                if (status != 0) {
                    fprintf(stderr, "Failed to read GPIO: %s\n", bladerf_strerror(status));
                    continue;
                }

                printf("\nWrite:\n");
                print_gpio_bits(write_val);
                printf("\nRead:\n");
                print_gpio_bits(read_val);

                int sum = (read_val >> 2) & 1;
                int cout = (read_val >> 3) & 1;
                printf("\nHalf-Adder Result: SUM=%d, COUT=%d\n", sum, cout);

                // Expected
                int expected_sum = a ^ b;
                int expected_cout = a & b;
                printf("Expected:          SUM=%d, COUT=%d %s\n",
                       expected_sum, expected_cout,
                       (sum == expected_sum && cout == expected_cout) ? "✓" : "✗");
            } else {
                printf("Invalid format. Use: t <a> <b>\n");
            }
        }
        else {
            printf("Unknown command. Use: r, w <hex>, t <a> <b>, or q\n");
        }

        printf("\n");
    }

    printf("Closing device...\n");
    bladerf_close(dev);
    return 0;
}
