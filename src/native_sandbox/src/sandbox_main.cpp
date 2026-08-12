#include <iostream>
#include <string>
#include "runner.hpp"

int main(int argc, char* argv[]) {
    native_sandbox::SandboxOptions options;
    if (argc > 1) {
        options.command = argv[1];
    } else {
        options.command = "echo Sandbox Engine Ready";
    }

    if (argc > 2) {
        options.timeout_ms = std::stoi(argv[2]);
    }

    if (argc > 3) {
        options.memory_limit_mb = std::stoi(argv[3]);
    }

    std::cout << "[SANDBOX] Running command: '" << options.command
              << "' (Timeout: " << options.timeout_ms << "ms, Memory Limit: "
              << options.memory_limit_mb << "MB)" << std::endl;

    auto result = native_sandbox::SandboxRunner::run(options);

    std::cout << "[SANDBOX] Success: " << (result.success ? "true" : "false") << std::endl;
    std::cout << "[SANDBOX] Exit Code: " << result.exit_code << std::endl;
    std::cout << "[SANDBOX] Timed Out: " << (result.timed_out ? "true" : "false") << std::endl;
    std::cout << "[SANDBOX] Duration: " << result.execution_time_ms << " ms" << std::endl;

    if (!result.stdout_output.empty()) {
        std::cout << "[SANDBOX STDOUT]\n" << result.stdout_output;
    }

    if (!result.stderr_output.empty()) {
        std::cerr << "[SANDBOX STDERR]\n" << result.stderr_output;
    }

    if (!result.error_message.empty()) {
        std::cerr << "[SANDBOX ERROR] " << result.error_message << std::endl;
    }

    return result.success ? 0 : 1;
}
