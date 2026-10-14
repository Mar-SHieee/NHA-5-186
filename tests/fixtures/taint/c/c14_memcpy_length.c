// c14_memcpy_length.c
// EXPECT: flow   (tainted LENGTH reaches memcpy argument 3; depends on atoi passing taint)
#include <stdlib.h>
#include <string.h>
void f_c14(char *src) {
    char a[64];
    size_t n = atoi(getenv("N"));
    memcpy(a, src, n);
}
