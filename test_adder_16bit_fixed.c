/*
 * 16-bit Adder Test for bladeRF FPGA (Fixed version with delays)
 *
 * Tests the 16-bit combinational adder accessible via config GPIO
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>  // for usleep
#include <libbladeRF.h>

#define TEST_PASSED "\033[32m[PASS]\033[0m"
#define TEST_FAILED "\033[31m[FAIL]\033[0m"

typedef struct {
    uint16_t a;
    uint16_t b;
    uint16_t expected_sum;
    uint8_t expected_carry;
    const char *description;
} test_case_t;

// Test cases for 16-bit adder
static const test_case_t test_cases[] = {
    // Basic tests
    {0, 0, 0, 0, "Zero + Zero"},
    {1, 1, 2, 0, "1 + 1"},
    {100, 200, 300, 0, "100 + 200"},
    {1000, 2000, 3000, 0, "1000 + 2000"},

    // Edge cases
    {65535, 0, 65535, 0, "Max value + 0"},
    {0, 65535, 65535, 0, "0 + Max value"},
    {1, 65535, 0, 1, "1 + 65535 (overflow)"},
    {65535, 1, 0, 1, "65535 + 1 (overflow)"},
    {65535, 65535, 65534, 1, "Max + Max (overflow)"},

    // Powers of 2
    {256, 256, 512, 0, "256 + 256"},
    {1024, 1024, 2048, 0, "1024 + 1024"},
    {32768, 32768, 0, 1, "32768 + 32768 (overflow)"},

    // Random values
    {12345, 54321, 1130, 1, "12345 + 54321 (overflow)"},
    {0xAAAA, 0x5555, 0xFFFF, 0, "0xAAAA + 0x5555"},
};

#define NUM_TEST_CASES (sizeof(test_cases) / sizeof(test_cases[0]))

/**
 * Write operands to config GPIO and read result with delay
 */
static int adder_compute(struct bladerf *dev, uint16_t a, uint16_t b,
                        uint16_t *sum, uint8_t *carry)
{
    int status;
    uint32_t gpio_val;

    // Pack both operands into 32-bit value
    // gpio_in[15:0]  = operand A
    // gpio_in[31:16] = operand B
    gpio_val = ((uint32_t)b << 16) | a;

    // Debug: print what we're writing
    // printf("  [DEBUG] Writing: 0x%08X (A=%u, B=%u)\n", gpio_val, a, b);

    // Write operands
    status = bladerf_config_gpio_write(dev, gpio_val);
    if (status != 0) {
        fprintf(stderr, "Failed to write GPIO: %s\n", bladerf_strerror(status));
        return status;
    }

    // CRITICAL: Add delay to let NIOS process the request
    usleep(10000);  // 10ms delay

    // Read result
    status = bladerf_config_gpio_read(dev, &gpio_val);
    if (status != 0) {
        fprintf(stderr, "Failed to read GPIO: %s\n", bladerf_strerror(status));
        return status;
    }

    // Debug: print what we read
    // printf("  [DEBUG] Read: 0x%08X\n", gpio_val);

    // Extract result
    // gpio_out[15:0] = sum
    // gpio_out[16]   = carry
    *sum = gpio_val & 0xFFFF;
    *carry = (gpio_val >> 16) & 0x1;

    // Another small delay between tests
    usleep(5000);  // 5ms delay

    return 0;
}

/**
 * Run a single test case
 */
static int run_test(struct bladerf *dev, const test_case_t *test)
{
    uint16_t actual_sum;
    uint8_t actual_carry;
    int status;

    status = adder_compute(dev, test->a, test->b, &actual_sum, &actual_carry);
    if (status != 0) {
        return status;
    }

    // Verify result
    int passed = (actual_sum == test->expected_sum) &&
                 (actual_carry == test->expected_carry);

    printf("%s %s\n", passed ? TEST_PASSED : TEST_FAILED, test->description);
    printf("        %u + %u = %u (carry=%u)\n",
           test->a, test->b, actual_sum, actual_carry);

    if (!passed) {
        printf("        Expected: %u (carry=%u)\n",
               test->expected_sum, test->expected_carry);
        printf("        Raw GPIO value difference: %d\n",
               (int)actual_sum - (int)test->expected_sum);
    }

    return passed ? 0 : -1;
}

/**
 * Main test function
 */
int main(int argc, char *argv[])
{
    struct bladerf *dev = NULL;
    int status;
    int passed = 0;
    int failed = 0;

    printf("===========================================\n");
    printf("  bladeRF 16-bit Adder Test Suite (Fixed)\n");
    printf("===========================================\n\n");

    // Open device
    status = bladerf_open(&dev, NULL);
    if (status != 0) {
        fprintf(stderr, "Failed to open bladeRF device: %s\n",
                bladerf_strerror(status));
        return 1;
    }

    printf("Device opened successfully\n");

    // Check device is responding
    uint32_t test_val;
    status = bladerf_config_gpio_read(dev, &test_val);
    if (status != 0) {
        fprintf(stderr, "Device not responding to GPIO read: %s\n",
                bladerf_strerror(status));
        bladerf_close(dev);
        return 1;
    }
    printf("Device responding (initial GPIO: 0x%08X)\n", test_val);

    printf("Running %zu test cases with delays...\n\n", NUM_TEST_CASES);

    // Run all test cases
    for (size_t i = 0; i < NUM_TEST_CASES; i++) {
        printf("Test %zu: ", i + 1);
        fflush(stdout);  // Flush output before test

        status = run_test(dev, &test_cases[i]);
        if (status == 0) {
            passed++;
        } else {
            failed++;

            // If device disconnected, stop testing
            uint32_t ping;
            if (bladerf_config_gpio_read(dev, &ping) != 0) {
                fprintf(stderr, "\n⚠️  Device disconnected! Stopping tests.\n");
                break;
            }
        }
        printf("\n");
    }

    // Summary
    printf("===========================================\n");
    printf("  Test Results:\n");
    printf("  Passed: %d/%zu\n", passed, NUM_TEST_CASES);
    printf("  Failed: %d/%zu\n", failed, NUM_TEST_CASES);
    printf("===========================================\n");

    if (failed == 0) {
        printf("\n\033[32m✓ All tests passed!\033[0m\n");
    } else {
        printf("\n\033[31m✗ Some tests failed!\033[0m\n");
        printf("\nNote: If results are off by 128, there may be a GPIO bit alignment issue.\n");
    }

    // Cleanup
    bladerf_close(dev);

    return (failed == 0) ? 0 : 1;
}
