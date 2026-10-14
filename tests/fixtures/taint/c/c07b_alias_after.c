// c07b_alias_after.c
// EXPECT: flow   (alias created after the read: ordinary assignment buf -> p)
#include <stdio.h>
#include <stdlib.h>
void f_c07b(void) {
    char buf[128];
    fgets(buf, sizeof buf, stdin);
    char *p = buf;
    system(p);
}
