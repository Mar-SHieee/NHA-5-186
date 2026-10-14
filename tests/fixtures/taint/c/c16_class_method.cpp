// c16_class_method.cpp
// EXPECT: flow   (sink inside a C++ class method called with a tainted argument)
#include <cstdlib>
class Runner {
public:
    void launch(const char *c) { system(c); }
};
void f_c16(void) {
    Runner r;
    r.launch(getenv("CMD"));
}
