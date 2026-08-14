# Makefile for 16-bit Adder Tests

CC = gcc
CFLAGS = -Wall -Wextra -O2
LDFLAGS = -lbladeRF

TARGETS = test_adder_16bit test_adder_16bit_fixed test_adder_small

all: $(TARGETS)

test_adder_16bit: test_adder_16bit.c
	$(CC) $(CFLAGS) -o test_adder_16bit test_adder_16bit.c $(LDFLAGS)

test_adder_16bit_fixed: test_adder_16bit_fixed.c
	$(CC) $(CFLAGS) -o test_adder_16bit_fixed test_adder_16bit_fixed.c $(LDFLAGS)

test_adder_small: test_adder_small.c
	$(CC) $(CFLAGS) -o test_adder_small test_adder_small.c $(LDFLAGS)

clean:
	rm -f $(TARGETS)

run: test_adder_16bit
	./test_adder_16bit

run-fixed: test_adder_16bit_fixed
	./test_adder_16bit_fixed

run-small: test_adder_small
	./test_adder_small

.PHONY: all clean run run-fixed run-small
