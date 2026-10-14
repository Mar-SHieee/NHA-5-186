// c09_bounded_check.c
// EXPECT: flow
#include <stdlib.h>
#include <string.h>
void f_c09(void) {
    char *c = getenv("CMD");
    if (strlen(c) < 8) {
        system(c);
    }
}
