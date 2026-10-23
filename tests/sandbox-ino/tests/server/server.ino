#include "ottu.hpp"

OTTUNITY_TEST(init) {
    bool server_init = true;
    TEST_ASSERT_TRUE(server_init);
}

OTTUNITY_TEST(start) {
    uint8_t server_start = 1;
    TEST_ASSERT_EQUAL_UINT8(1, server_start);
}

OTTUNITY_TEST(stop) {
    void (*deamon_fn)() = NULL;
    TEST_ASSERT_NULL(deamon_fn);
}

OTTUNITY_RUN();