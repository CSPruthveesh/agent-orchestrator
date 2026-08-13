#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "runner.hpp"

namespace py = pybind11;

py::dict execute_sandboxed_code(const std::string& command, int timeout_ms = 5000, int memory_limit_mb = 256) {
    native_sandbox::SandboxOptions options;
    options.command = command;
    options.timeout_ms = timeout_ms;
    options.memory_limit_mb = memory_limit_mb;

    auto result = native_sandbox::SandboxRunner::run(options);

    py::dict res;
    res["success"] = result.success;
    res["exit_code"] = result.exit_code;
    res["stdout_output"] = result.stdout_output;
    res["stderr_output"] = result.stderr_output;
    res["execution_time_ms"] = result.execution_time_ms;
    res["timed_out"] = result.timed_out;
    res["memory_exceeded"] = result.memory_exceeded;
    res["error_message"] = result.error_message;

    return res;
}

PYBIND11_MODULE(native_sandbox_cpp, m) {
    m.doc() = "Native C++ execution sandbox bindings for Python";
    m.def(
        "execute_sandboxed_code",
        &execute_sandboxed_code,
        py::arg("command"),
        py::arg("timeout_ms") = 5000,
        py::arg("memory_limit_mb") = 256,
        "Execute a command in native sandboxed environment with resource quotas"
    );
}
