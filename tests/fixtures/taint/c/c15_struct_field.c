// c15_struct_field.c
// EXPECT: flow
#include <stdlib.h>
struct job { char *cmd; };
void f_c15(void) {
    struct job s;
    s.cmd = getenv("CMD");
    system(s.cmd);
}
