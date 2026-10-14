// c06_overwrite.c
// EXPECT: no-flow
#include <stdlib.h>
void f_c06(void) {
    char *c = getenv("CMD");
    c = "ls";
    system(c);
}
