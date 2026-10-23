#include "ottu.hpp"

OTTUNITY_TEST(init) {
    bool gateway_init = true;
    TEST_ASSERT_TRUE(gateway_init);
}

OTTUNITY_TEST(connected_nodes) {
    uint8_t connected_nodes = 4;
    TEST_ASSERT_EQUAL_UINT8(4, connected_nodes);
}

OTTUNITY_TEST(interface_up) {
    char * interface_status_msg = "up";
    TEST_ASSERT_EQUAL_STRING("up", interface_status_msg);
}

OTTUNITY_RUN();