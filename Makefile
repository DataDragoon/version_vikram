# Makefile for 16-bit Adder Test

CC = gcc
CFLAGS = -Wall -Wextra -O2
LDFLAGS = -lbladeRF

TARGET = test_adder_16bit
SRC = test_adder_16bit.c

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $(TARGET) $(SRC) $(LDFLAGS)

clean:
	rm -f $(TARGET)

run: $(TARGET)
	./$(TARGET)

.PHONY: all clean run
