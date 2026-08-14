/*
 * Direct test using backend expansion GPIO functions
 * This bypasses the board layer and calls backend directly
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
#include <libbladeRF.h>  // Includes both bladeRF1.h and bladeRF2.h

/* From nios_access.h - these are backend functions */
extern int nios_expansion_gpio_read(struct bladerf *dev, uint32_t *val);
extern int nios_expansion_gpio_write(struct bladerf *dev, uint32_t mask, uint32_t val);
extern int nios_expansion_gpio_dir_read(struct bladerf *dev, uint32_t *val);
extern int nios_expansion_gpio_dir_write(struct bladerf *dev, uint32_t mask, uint32_t val);

int main(int argc, char *argv[]) {
    struct bladerf *dev = NULL;
    int status;

    printf("Opening bladeRF device...\n");
    status = bladerf_open(&dev, NULL);
    if (status != 0) {
        fprintf(stderr, "Failed to open device: %s\n", bladerf_strerror(status));
        return 1;
    }

    if (argc > 1) {
        printf("Loading FPGA image: %s\n", argv[1]);
        status = bladerf_load_fpga(dev, argv[1]);
        if (status != 0) {
            fprintf(stderr, "Failed to load FPGA: %s\n", bladerf_strerror(status));
            bladerf_close(dev);
            return 1;
        }
        sleep(1);
    }

    printf("\n=== Testing Backend Expansion GPIO ===\n\n");

    /* Set direction: bits 0,1 as outputs (we write), bits 2,3 as inputs (we read) */
    uint32_t dir_mask = 0x03;  /* Configure bits 0,1 */
    uint32_t dir_val = 0x03;   /* Set as outputs */

    printf("Setting GPIO direction (bits 0,1 = output)...\n");
    status = nios_expansion_gpio_dir_write(dev, dir_mask, dir_val);
    if (status != 0) {
        fprintf(stderr, "Failed to set direction: %s\n", bladerf_strerror(status));
    }

    /* Read back direction */
    uint32_t dir_readback;
    status = nios_expansion_gpio_dir_read(dev, &dir_readback);
    printf("Direction readback: 0x%08X\n\n", dir_readback);

    /* Test all combinations */
    int test_cases[][4] = {
        {0, 0, 0, 0},
        {0, 1, 1, 0},
        {1, 0, 1, 0},
        {1, 1, 0, 1},
    };

    for (int i = 0; i < 4; i++) {
        int a = test_cases[i][0];
        int b = test_cases[i][1];
        int expected_sum = test_cases[i][2];
        int expected_cout = test_cases[i][3];

        uint32_t write_val = (b << 1) | a;
        uint32_t write_mask = 0x03;  /* Write to bits 0,1 */

        printf("Test A=%d, B=%d (writing 0x%X)...\n", a, b, write_val);

        status = nios_expansion_gpio_write(dev, write_mask, write_val);
        if (status != 0) {
            fprintf(stderr, "  Write failed: %s\n", bladerf_strerror(status));
            continue;
        }

        usleep(10000);  /* 10ms delay */

        uint32_t read_val;
        status = nios_expansion_gpio_read(dev, &read_val);
        if (status != 0) {
            fprintf(stderr, "  Read failed: %s\n", bladerf_strerror(status));
            continue;
        }

        int sum = (read_val >> 2) & 1;
        int cout = (read_val >> 3) & 1;

        printf("  Read: 0x%08X -> SUM=%d, COUT=%d (expected SUM=%d, COUT=%d) %s\n",
               read_val, sum, cout, expected_sum, expected_cout,
               (sum == expected_sum && cout == expected_cout) ? "✓" : "✗");
    }

    printf("\n");
    bladerf_close(dev);
    return 0;
}
