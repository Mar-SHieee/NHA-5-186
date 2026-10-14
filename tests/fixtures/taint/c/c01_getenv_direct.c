// c01_getenv_direct.c
// EXPECT: flow
#include <stdlib.h>
void f_c01(void) {
    char *c = getenv("CMD");
    system(c);
}
