cmake_minimum_required(VERSION 3.20)

project(BatteryController)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(BatteryController
    src/main.cpp
    src/controller.cpp
    src/mqtt_client.cpp
    src/debug.cpp
    src/json_serializer.cpp
)

target_include_directories(BatteryController PRIVATE ${PROJECT_SOURCE_DIR}/include)
target_link_directories(BatteryController PRIVATE /clang64/lib)
target_link_libraries(BatteryController PRIVATE mosquitto)

