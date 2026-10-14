// c03_fgets_outparam.c
// EXPECT: flow
#include <stdio.h>
#include <stdlib.h>
void f_c03(void) {
    char buf[128];
    fgets(buf, sizeof buf, stdin);
    system(buf);
}
