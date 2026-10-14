// c11_read_outparam.c
// EXPECT: flow
#include <unistd.h>
#include <stdlib.h>
void f_c11(void) {
    char buf[128];
    read(0, buf, sizeof buf);
    system(buf);
}
