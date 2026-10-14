// c18_cpp_static_call.cpp
// EXPECT: flow   (static method call, sink inside the callee)
#include <cstdlib>
class Stat {
public:
    static void launch_s(const char *c) { system(c); }
};
void f_c18(void) {
    Stat::launch_s(getenv("CMD"));
}
