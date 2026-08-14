/*
 * Small Value Adder Test for bladeRF FPGA
 *
 * Tests 16-bit adder with small values to avoid bit 7 issue
 * This helps isolate whether the problem is in the adder logic
 * or just the GPIO bit mapping.
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
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

// Test cases using only small values (avoiding bit 7 = 128)
static const test_case_t test_cases[] = {
    // Basic tests (no bit 7)
    {0, 0, 0, 0, "Zero + Zero"},
    {1, 1, 2, 0, "1 + 1"},
    {1, 2, 3, 0, "1 + 2"},
    {5, 5, 10, 0, "5 + 5"},
    {10, 10, 20, 0, "10 + 10"},
    {10, 20, 30, 0, "10 + 20"},
    {25, 25, 50, 0, "25 + 25"},
    {30, 40, 70, 0, "30 + 40"},
    {50, 50, 100, 0, "50 + 50"},
    {60, 67, 127, 0, "60 + 67 = 127 (max without bit 7)"},

    // Edge case: Just below bit 7
    {127, 0, 127, 0, "127 + 0"},
    {0, 127, 127, 0, "0 + 127"},
    {63, 64, 127, 0, "63 + 64"},
};

#define NUM_TEST_CASES (sizeof(test_cases) / sizeof(test_cases[0]))

/**
 * Write operands to config GPIO and read result
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

    // Write operands
    status = bladerf_config_gpio_write(dev, gpio_val);
    if (status != 0) {
        fprintf(stderr, "Failed to write GPIO: %s\n", bladerf_strerror(status));
        return status;
    }

    // Add delay to let NIOS process
    usleep(10000);  // 10ms

    // Read result
    status = bladerf_config_gpio_read(dev, &gpio_val);
    if (status != 0) {
        fprintf(stderr, "Failed to read GPIO: %s\n", bladerf_strerror(status));
        return status;
    }

    // Extract result
    *sum = gpio_val & 0xFFFF;
    *carry = (gpio_val >> 16) & 0x1;

    // Small delay between tests
    usleep(5000);  // 5ms

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
        printf("        Difference: %d\n",
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
    printf("  bladeRF 16-bit Adder Small Value Test\n");
    printf("  (Testing values < 128 to avoid bit 7)\n");
    printf("===========================================\n\n");

    // Open device
    status = bladerf_open(&dev, NULL);
    if (status != 0) {
        fprintf(stderr, "Failed to open bladeRF device: %s\n",
                bladerf_strerror(status));
        return 1;
    }

    printf("Device opened successfully\n");

    // Verify device is responding
    uint32_t test_val;
    status = bladerf_config_gpio_read(dev, &test_val);
    if (status != 0) {
        fprintf(stderr, "Device not responding: %s\n",
                bladerf_strerror(status));
        bladerf_close(dev);
        return 1;
    }
    printf("Device responding (GPIO: 0x%08X)\n", test_val);

    printf("Running %zu test cases...\n\n", NUM_TEST_CASES);

    // Run all test cases
    for (size_t i = 0; i < NUM_TEST_CASES; i++) {
        printf("Test %zu: ", i + 1);
        fflush(stdout);

        status = run_test(dev, &test_cases[i]);
        if (status == 0) {
            passed++;
        } else {
            failed++;

            // Check if device is still connected
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
        printf("\nThe adder logic works correctly for small values.\n");
        printf("The issue with larger values is likely a GPIO bit 7 problem.\n");
    } else {
        printf("\n\033[31m✗ Some tests failed!\033[0m\n");
        printf("\nEven small values fail - this indicates a deeper problem.\n");
    }

    // Cleanup
    bladerf_close(dev);

    return (failed == 0) ? 0 : 1;
}
