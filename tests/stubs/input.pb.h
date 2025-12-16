#ifndef INPUT_PB_H
#define INPUT_PB_H

#include <stdint.h>
#include <stdbool.h>
#include "pb_decode.h"

/* Struct definitions */
typedef struct _test_func_Params {
    bool has_param_0;
    int32_t param_0;
} test_func_Params;

/* Initializer values (nanopb-style) */
#define test_func_Params_init_zero {false, 0}

typedef struct _FuzzInput {
    pb_size_t test_func_count;
    test_func_Params test_func[4]; 
} FuzzInput;

/* Initializer values */
#define FuzzInput_init_zero {0, {}}

/* Field descriptions */
extern const pb_msgdesc_t FuzzInput_fields[1];

#endif
