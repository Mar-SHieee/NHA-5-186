// c13_scanf_outparam.c
// EXPECT: flow
#include <stdio.h>
#include <stdlib.h>
void f_c13(void) {
    char buf[128];
    scanf("%127s", buf);
    system(buf);
}
