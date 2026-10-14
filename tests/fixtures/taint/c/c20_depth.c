// c20_depth.c
// EXPECT: flow for all six entries (ground truth); the question is how many the default depth follows
#include <stdlib.h>
void h1(char *c) { system(c); }
void h2(char *c) { h1(c); }
void h3(char *c) { h2(c); }
void h4(char *c) { h3(c); }
void h5(char *c) { h4(c); }
void h6(char *c) { h5(c); }
void e1(void) { h1(getenv("DEPTH_A")); }
void e2(void) { h2(getenv("DEPTH_B")); }
void e3(void) { h3(getenv("DEPTH_C")); }
void e4(void) { h4(getenv("DEPTH_D")); }
void e5(void) { h5(getenv("DEPTH_E")); }
void e6(void) { h6(getenv("DEPTH_F")); }
