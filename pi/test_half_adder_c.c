/*
 * Test half-adder on bladeRF FPGA using expansion GPIO
 * Compile: gcc test_half_adder_c.c -o test_half_adder_c -lbladeRF
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
#include <libbladeRF.h>

void set_inputs(struct bladerf *dev, int a, int b) {
    uint32_t val = (b << 1) | a;  // bit 0 = A, bit 1 = B
    int status = bladerf_config_gpio_write(dev, val);
    if (status != 0) {
        fprintf(stderr, "Failed to write GPIO: %s\n", bladerf_strerror(status));
    }
    usleep(1000);  // 1ms delay
}

void read_outputs(struct bladerf *dev, int *sum, int *cout) {
    uint32_t val;
    int status = bladerf_config_gpio_read(dev, &val);
    if (status != 0) {
        fprintf(stderr, "Failed to read GPIO: %s\n", bladerf_strerror(status));
        *sum = -1;
        *cout = -1;
        return;
    }

    *sum = (val >> 2) & 0x01;   // bit 2 = SUM
    *cout = (val >> 3) & 0x01;  // bit 3 = COUT
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

    // Test half-adder
    printf("\n");
    printf("==================================================\n");
    printf("Testing Half-Adder on FPGA\n");
    printf("==================================================\n");

    int test_vectors[][4] = {
        {0, 0, 0, 0},  // A=0, B=0 -> SUM=0, COUT=0
        {0, 1, 1, 0},  // A=0, B=1 -> SUM=1, COUT=0
        {1, 0, 1, 0},  // A=1, B=0 -> SUM=1, COUT=0
        {1, 1, 0, 1},  // A=1, B=1 -> SUM=0, COUT=1
    };

    int all_passed = 1;

    for (int i = 0; i < 4; i++) {
        int a = test_vectors[i][0];
        int b = test_vectors[i][1];
        int expected_sum = test_vectors[i][2];
        int expected_cout = test_vectors[i][3];

        set_inputs(dev, a, b);

        int sum, cout;
        read_outputs(dev, &sum, &cout);

        int passed = (sum == expected_sum) && (cout == expected_cout);
        printf("A=%d, B=%d -> SUM=%d, COUT=%d (expected SUM=%d, COUT=%d) %s\n",
               a, b, sum, cout, expected_sum, expected_cout,
               passed ? "✓ PASS" : "✗ FAIL");

        if (!passed) {
            all_passed = 0;
        }
    }

    printf("==================================================\n");
    if (all_passed) {
        printf("✓ All tests PASSED!\n");
    } else {
        printf("✗ Some tests FAILED!\n");
    }
    printf("==================================================\n");

    bladerf_close(dev);
    return all_passed ? 0 : 1;
}
