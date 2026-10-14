// c17_cpp_same_method.cpp
// EXPECT: flow   (source and sink inside one class method, no cross-function step)
#include <cstdlib>
class Local {
public:
    void go() {
        char *c = getenv("CMD");
        system(c);
    }
};
