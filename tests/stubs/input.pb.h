#ifndef INPUT_PB_H
#define INPUT_PB_H

#include <stdint.h>
#include "pb_decode.h"

/* Struct definitions */
typedef struct _test_func_Params {
    int32_t param1;
} test_func_Params;

typedef struct _FuzzInput {
    pb_size_t test_func_count;
    test_func_Params test_func[4]; 
} FuzzInput;

/* Initializer values */
#define FuzzInput_init_zero {0, {}}

/* Field descriptions */
extern const pb_msgdesc_t FuzzInput_fields[1];

#endif
