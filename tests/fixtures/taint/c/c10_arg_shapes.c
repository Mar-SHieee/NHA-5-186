// c10_arg_shapes.c
// Not a flow fixture: used to read argument indices of libc calls.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
void f_c10(int fd, char *src, size_t n) {
    char a[64];
    char b[64];
    strcpy(a, src);
    strcat(a, src);
    memcpy(a, src, n);
    sprintf(a, "%s", src);
    gets(a);
    read(fd, b, sizeof b);
    recv(fd, b, sizeof b, 0);
    scanf("%s", b);
    fopen(src, "r");
    popen(src, "r");
}
