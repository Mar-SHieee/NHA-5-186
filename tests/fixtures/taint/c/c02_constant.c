// c02_constant.c
// EXPECT: no-flow
#include <stdlib.h>
void f_c02(void) {
    char *c = getenv("CMD");
    system("ls");
}
