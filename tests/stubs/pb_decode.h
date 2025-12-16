#ifndef PB_DECODE_H
#define PB_DECODE_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#include "pb.h"
typedef struct pb_msgdesc_s pb_msgdesc_t;

struct pb_msgdesc_s {
    const void * ptr; // Dummy definition for size
};

typedef struct pb_istream_s pb_istream_t;

struct pb_istream_s {
    bool (*callback)(pb_istream_t *stream, uint8_t *buf, size_t count);
    void *state;
    size_t bytes_left;
};

pb_istream_t pb_istream_from_buffer(const uint8_t *buf, size_t bufsize);
bool pb_decode(pb_istream_t *stream, const pb_msgdesc_t *fields, void *dest_struct);

#endif
