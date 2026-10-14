// c07c_alias_source.c
// EXPECT: flow   (the read goes through the alias p, the sink uses buf)
#include <stdio.h>
#include <stdlib.h>
void f_c07c(void) {
    char buf[128];
    char *p = buf;
    fgets(p, sizeof buf, stdin);
    system(buf);
}
