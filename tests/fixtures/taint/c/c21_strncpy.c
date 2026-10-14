// c21_strncpy.c
// EXPECT: flow   (a bounded copy does not stop command injection; strncpy should appear in the path)
#include <stdlib.h>
#include <string.h>
void f_c21(void) {
    char buf[64];
    char *c = getenv("CMD");
    strncpy(buf, c, sizeof buf - 1);
    system(buf);
}
