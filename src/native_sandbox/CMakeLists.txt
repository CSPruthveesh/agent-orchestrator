cmake_minimum_required(VERSION 3.20)
project(native_sandbox LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(MINGW)
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -static -static-libgcc -static-libstdc++")
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -static-libgcc -static-libstdc++")
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

# Find Python & pybind11
find_package(Python 3.14 COMPONENTS Interpreter Development REQUIRED)

execute_process(
    COMMAND "${Python_EXECUTABLE}" -c "import pybind11; print(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE PYBIND11_CMAKE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
list(APPEND CMAKE_PREFIX_PATH "${PYBIND11_CMAKE_DIR}")

find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(native_sandbox_cpp
    bindings/pybind_module.cpp
)

target_link_libraries(native_sandbox_cpp PRIVATE sandbox_runner)

# Output directory for Python extension module
set_target_properties(native_sandbox_cpp PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../backend/tools"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../backend/tools"
)
