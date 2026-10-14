// c08_snprintf.c
// EXPECT: flow
#include <stdio.h>
#include <stdlib.h>
void f_c08(void) {
    char cmd[256];
    char *c = getenv("DIR");
    snprintf(cmd, sizeof cmd, "ls %s", c);
    system(cmd);
}
