// c24_copy_functions.c
// EXPECT: flow for all seven (every copy carries the tainted bytes to system)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
void f_c24a(void) { char buf[64]; char *c = getenv("CMD"); strcpy(buf, c); system(buf); }
void f_c24b(void) { char buf[64]; char *c = getenv("CMD"); strncpy(buf, c, sizeof buf - 1); system(buf); }
void f_c24c(void) { char buf[64] = ""; char *c = getenv("CMD"); strcat(buf, c); system(buf); }
void f_c24d(void) { char buf[64] = ""; char *c = getenv("CMD"); strncat(buf, c, sizeof buf - 1); system(buf); }
void f_c24e(void) { char buf[64]; char *c = getenv("CMD"); memcpy(buf, c, 16); system(buf); }
void f_c24f(void) { char buf[64]; char *c = getenv("CMD"); sprintf(buf, "%s", c); system(buf); }
void f_c24g(void) { char buf[64]; char *c = getenv("CMD"); strncpy(buf, c, 63); system(buf); }
