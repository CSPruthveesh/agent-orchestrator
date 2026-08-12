#ifndef SANDBOX_RUNNER_HPP
#define SANDBOX_RUNNER_HPP

#include <string>
#include <chrono>

namespace native_sandbox {

struct SandboxOptions {
    std::string command;
    int timeout_ms = 5000;
    int memory_limit_mb = 256;
};

struct ExecutionResult {
    bool success = false;
    int exit_code = -1;
    std::string stdout_output;
    std::string stderr_output;
    long long execution_time_ms = 0;
    bool timed_out = false;
    bool memory_exceeded = false;
    std::string error_message;
};

class SandboxRunner {
public:
    static ExecutionResult run(const SandboxOptions& options);
};

} // namespace native_sandbox

#endif // SANDBOX_RUNNER_HPP
