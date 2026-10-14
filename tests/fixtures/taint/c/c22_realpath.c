// c22_realpath.c
// EXPECT: flow for both (realpath alone does not confine the path; candidate sanitizer, must be visible in the path)
#include <stdio.h>
#include <stdlib.h>
void f_c22a(void) {
    char resolved[4096];
    char *p = getenv("FILE");
    realpath(p, resolved);
    fopen(resolved, "r");
}
void f_c22b(void) {
    char *p = getenv("FILE");
    char *r = realpath(p, NULL);
    fopen(r, "r");
}
