// c04_argv.c
// EXPECT: flow
#include <string.h>
void f_c04(int argc, char **argv) {
    char buf[16];
    strcpy(buf, argv[1]);
}
