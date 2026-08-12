#include <iostream>
#include <cassert>
#include "runner.hpp"

void test_basic_execution() {
    native_sandbox::SandboxOptions options;
    options.command = "whoami";
    options.timeout_ms = 3000;
    options.memory_limit_mb = 256;

    auto result = native_sandbox::SandboxRunner::run(options);
    assert(result.exit_code == 0);
    assert(result.success == true);
    assert(result.timed_out == false);
    assert(!result.stdout_output.empty());
    std::cout << "[PASS] Basic process execution & pipe capture verified" << std::endl;
}

void test_timeout_enforcement() {
    native_sandbox::SandboxOptions options;
    options.command = "powershell -Command Start-Sleep -Seconds 3";
    options.timeout_ms = 500;
    options.memory_limit_mb = 256;

    auto result = native_sandbox::SandboxRunner::run(options);
    assert(result.timed_out == true);
    assert(result.success == false);
    std::cout << "[PASS] Execution timeout enforcement & process termination verified" << std::endl;
}

int main() {
    std::cout << "=== Running Native Sandbox Unit Tests ===" << std::endl;
    test_basic_execution();
    test_timeout_enforcement();
    std::cout << "=== All Native Sandbox Unit Tests Passed Successfully! ===" << std::endl;
    return 0;
}
