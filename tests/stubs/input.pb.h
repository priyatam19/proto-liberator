#ifndef INPUT_PB_H
#define INPUT_PB_H

#include <stdint.h>
#include <stdbool.h>
#include "pb.h"

/* Struct definitions */
typedef struct _test_func_Params {
    bool has_param_0_handle;
    uint32_t param_0_handle;
    bool has_param_0_is_null;
    bool param_0_is_null;

    bool has_param_1;
    pb_bytes_array_t param_1;
    bool has_param_1_length;
    uint32_t param_1_length;
    bool has_param_1_length_override;
    uint32_t param_1_length_override;
    bool has_param_1_is_null;
    bool param_1_is_null;

    bool has_skip_dependency_check;
    bool skip_dependency_check;
    bool has_allow_double_delete;
    bool allow_double_delete;
} test_func_Params;

#define test_func_Params_init_zero {false, 0, false, false, false, {0,{0}}, false, 0, false, 0, false, false, false, false, false, false}

typedef struct _Action {
    pb_size_t which_action;
    union {
        test_func_Params test_func;
    } action;
} Action;

#define Action_init_zero {0, {test_func_Params_init_zero}}

/* Oneof tags */
#define Action_test_func_tag 1

typedef struct _FuzzInput {
    pb_size_t actions_count;
    Action actions[4]; 
} FuzzInput;

#define FuzzInput_init_zero {0, {Action_init_zero, Action_init_zero, Action_init_zero, Action_init_zero}}

/* Field descriptions */
extern const pb_msgdesc_t FuzzInput_fields[1];

#endif
