// c12_recv_outparam.c
// EXPECT: flow
#include <sys/socket.h>
#include <stdlib.h>
void f_c12(int s) {
    char buf[128];
    recv(s, buf, sizeof buf, 0);
    system(buf);
}
