// c07_alias.c
// EXPECT: flow
#include <stdio.h>
#include <stdlib.h>
void f_c07(void) {
    char buf[128];
    char *p = buf;
    fgets(buf, sizeof buf, stdin);
    system(p);
}
