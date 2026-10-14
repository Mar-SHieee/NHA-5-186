// c05_cross_function.c
// EXPECT: flow for both
#include <stdlib.h>
char *read_cmd(void) { return getenv("CMD"); }
void run(char *c) { system(c); }

void f_c05a(void) {
    system(read_cmd());
}
void f_c05b(void) {
    run(getenv("CMD"));
}
