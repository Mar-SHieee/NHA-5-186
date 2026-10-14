// c19_cpp_member_to_member.cpp
// EXPECT: flow   (unqualified call to another member of the same class)
#include <cstdlib>
class Inner {
public:
    void sink_c19(const char *c) { system(c); }
    void entry_c19() { sink_c19(getenv("CMD")); }
};
