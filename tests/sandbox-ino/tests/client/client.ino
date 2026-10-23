#include "ottu.hpp"

OTTUNITY_TEST(init) {
    bool client_init = true;
    TEST_ASSERT_TRUE(client_init);
}

OTTUNITY_TEST(connect) {
    uint8_t client_connected = 1;
    TEST_ASSERT_EQUAL_UINT8(1, client_connected);
}

OTTUNITY_TEST(disconnect) {
    void (*is_client_connected_fn)() = NULL;
    TEST_ASSERT_NULL(is_client_connected_fn);
}

OTTUNITY_RUN();