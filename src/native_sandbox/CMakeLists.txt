cmake_minimum_required(VERSION 3.20)
project(native_sandbox LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(MINGW)
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -static -static-libgcc -static-libstdc++")
endif()

include_directories(${CMAKE_CURRENT_SOURCE_DIR}/src)

# Sandbox Runner Static Library
add_library(sandbox_runner STATIC
    src/runner.cpp
    src/runner.hpp
)

# CLI Harness Executable
add_executable(sandbox_main
    src/sandbox_main.cpp
)

target_link_libraries(sandbox_main PRIVATE sandbox_runner)

# Native Unit Test Executable
add_executable(test_sandbox
    ${CMAKE_CURRENT_SOURCE_DIR}/../../tests/native/test_sandbox.cpp
)

target_link_libraries(test_sandbox PRIVATE sandbox_runner)
