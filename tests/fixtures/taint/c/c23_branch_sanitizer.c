// c23_branch_sanitizer.c
// EXPECT: flow   (the path that skips shell_escape is unsanitized; shell_escape is deliberately undefined)
#include <stdlib.h>
char *shell_escape(char *s);
void f_c23(int flag) {
    char *c = getenv("CMD");
    if (flag) {
        c = shell_escape(c);
    }
    system(c);
}
