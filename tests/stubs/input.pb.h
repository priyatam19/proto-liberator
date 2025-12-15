#ifndef INPUT_PB_H
#define INPUT_PB_H

#include <stdint.h>
#include "pb_decode.h"

/* Struct definitions */
typedef struct _test_func_Params {
    int32_t param1;
} test_func_Params;

typedef struct _ApiCall {
    pb_size_t which_call;
    union {
        test_func_Params test_func;
    } call;
} ApiCall;

typedef struct _FuzzInput {
    pb_size_t api_calls_count;
    ApiCall api_calls[10]; 
} FuzzInput;

/* Initializer values */
#define FuzzInput_init_zero {0, {}}

/* Field descriptions */
extern const pb_msgdesc_t FuzzInput_fields[1];

/* Tags */
#define ApiCall_call_test_func_tag 1

#endif
