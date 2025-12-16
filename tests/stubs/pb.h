#ifndef PB_H
#define PB_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/* Minimal subset of nanopb pb.h needed for compile-only tests. */
typedef uint16_t pb_size_t;
typedef uint8_t pb_byte_t;

typedef struct pb_bytes_array_s {
    pb_size_t size;
    pb_byte_t bytes[1];
} pb_bytes_array_t;

#endif

