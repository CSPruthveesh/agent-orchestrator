#include "runner.hpp"

#include <iostream>
#include <sstream>
#include <thread>
#include <vector>
#include <array>
#include <cstdio>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <fcntl.h>
#include <signal.h>
#endif

namespace native_sandbox {

#ifdef _WIN32

ExecutionResult SandboxRunner::run(const SandboxOptions& options) {
    ExecutionResult result;
    auto start_time = std::chrono::high_resolution_clock::now();

    // Configure Security Attributes for Pipe Inheritance
    SECURITY_ATTRIBUTES saAttr;
    saAttr.nLength = sizeof(SECURITY_ATTRIBUTES);
    saAttr.bInheritHandle = TRUE;
    saAttr.lpSecurityDescriptor = NULL;

    HANDLE hChildStd_OUT_Rd = NULL;
    HANDLE hChildStd_OUT_Wr = NULL;
    HANDLE hChildStd_ERR_Rd = NULL;
    HANDLE hChildStd_ERR_Wr = NULL;

    // Create stdout pipe & disable inherit on read handle
    if (!CreatePipe(&hChildStd_OUT_Rd, &hChildStd_OUT_Wr, &saAttr, 0) ||
        !SetHandleInformation(hChildStd_OUT_Rd, HANDLE_FLAG_INHERIT, 0)) {
        result.error_message = "Failed to create stdout pipe";
        return result;
    }

    // Create stderr pipe & disable inherit on read handle
    if (!CreatePipe(&hChildStd_ERR_Rd, &hChildStd_ERR_Wr, &saAttr, 0) ||
        !SetHandleInformation(hChildStd_ERR_Rd, HANDLE_FLAG_INHERIT, 0)) {
        result.error_message = "Failed to create stderr pipe";
        CloseHandle(hChildStd_OUT_Rd);
        CloseHandle(hChildStd_OUT_Wr);
        return result;
    }

    // Configure Job Object for Process Isolation
    HANDLE hJob = CreateJobObjectW(NULL, NULL);
    if (hJob != NULL) {
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli = { 0 };
        jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(hJob, JobObjectExtendedLimitInformation, &jeli, sizeof(jeli));
    }

    // Process Startup Info
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(STARTUPINFOA));
    si.cb = sizeof(STARTUPINFOA);
    si.hStdOutput = hChildStd_OUT_Wr;
    si.hStdError = hChildStd_ERR_Wr;
    si.dwFlags |= STARTF_USESTDHANDLES;
    ZeroMemory(&pi, sizeof(PROCESS_INFORMATION));

    std::string cmd = "cmd.exe /c " + options.command;
    std::vector<char> cmd_buffer(cmd.begin(), cmd.end());
    cmd_buffer.push_back('\0');

    BOOL success = CreateProcessA(
        NULL,
        cmd_buffer.data(),
        NULL,
        NULL,
        TRUE,
        0,
        NULL,
        NULL,
        &si,
        &pi
    );

    if (!success) {
        DWORD err = GetLastError();
        result.error_message = "Failed to spawn process (Windows Error Code: " + std::to_string(err) + ")";
        CloseHandle(hChildStd_OUT_Rd);
        CloseHandle(hChildStd_OUT_Wr);
        CloseHandle(hChildStd_ERR_Rd);
        CloseHandle(hChildStd_ERR_Wr);
        if (hJob) CloseHandle(hJob);
        return result;
    }

    if (hJob != NULL) {
        AssignProcessToJobObject(hJob, pi.hProcess);
    }

    // Close write handles in parent process
    CloseHandle(hChildStd_OUT_Wr);
    CloseHandle(hChildStd_ERR_Wr);

    // 1. FIRST: Wait for process completion or timeout
    DWORD wait_res = WaitForSingleObject(pi.hProcess, static_cast<DWORD>(options.timeout_ms));

    if (wait_res == WAIT_TIMEOUT) {
        result.timed_out = true;
        result.error_message = "Execution timed out after " + std::to_string(options.timeout_ms) + " ms";
        TerminateProcess(pi.hProcess, 1);
        result.exit_code = -1;
        result.success = false;
    } else {
        DWORD exit_code = 0;
        if (GetExitCodeProcess(pi.hProcess, &exit_code)) {
            result.exit_code = static_cast<int>(exit_code);
            result.success = (exit_code == 0);
        }
    }

    // 2. SECOND: Read non-blocking stdout/stderr after process state resolved
    DWORD bytesAvail = 0;
    char buffer[1024];

    if (PeekNamedPipe(hChildStd_OUT_Rd, NULL, 0, NULL, &bytesAvail, NULL) && bytesAvail > 0) {
        DWORD bytesRead = 0;
        while (ReadFile(hChildStd_OUT_Rd, buffer, sizeof(buffer) - 1, &bytesRead, NULL) && bytesRead > 0) {
            buffer[bytesRead] = '\0';
            result.stdout_output += buffer;
        }
    }

    if (PeekNamedPipe(hChildStd_ERR_Rd, NULL, 0, NULL, &bytesAvail, NULL) && bytesAvail > 0) {
        DWORD bytesRead = 0;
        while (ReadFile(hChildStd_ERR_Rd, buffer, sizeof(buffer) - 1, &bytesRead, NULL) && bytesRead > 0) {
            buffer[bytesRead] = '\0';
            result.stderr_output += buffer;
        }
    }

    CloseHandle(hChildStd_OUT_Rd);
    CloseHandle(hChildStd_ERR_Rd);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    if (hJob) CloseHandle(hJob);

    auto end_time = std::chrono::high_resolution_clock::now();
    result.execution_time_ms = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time).count();

    return result;
}

#else

ExecutionResult SandboxRunner::run(const SandboxOptions& options) {
    ExecutionResult result;
    auto start_time = std::chrono::high_resolution_clock::now();

    int out_pipe[2];
    int err_pipe[2];
    if (pipe(out_pipe) < 0 || pipe(err_pipe) < 0) {
        result.error_message = "Failed to create execution pipes";
        return result;
    }

    pid_t pid = fork();
    if (pid < 0) {
        result.error_message = "Failed to fork child process";
        return result;
    }

    if (pid == 0) {
        // Child process
        close(out_pipe[0]);
        close(err_pipe[0]);
        dup2(out_pipe[1], STDOUT_FILENO);
        dup2(err_pipe[1], STDERR_FILENO);
        close(out_pipe[1]);
        close(err_pipe[1]);

        // Memory limit
        rlimit mem_limit;
        mem_limit.rlim_cur = static_cast<rlim_t>(options.memory_limit_mb) * 1024 * 1024;
        mem_limit.rlim_max = mem_limit.rlim_cur;
        setrlimit(RLIMIT_AS, &mem_limit);

        // Execute command
        execl("/bin/sh", "sh", "-c", options.command.c_str(), (char*)NULL);
        _exit(127);
    }

    // Parent Process
    close(out_pipe[1]);
    close(err_pipe[1]);

    int status = 0;
    auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(options.timeout_ms);
    bool finished = false;

    while (std::chrono::steady_clock::now() < deadline) {
        pid_t res = waitpid(pid, &status, WNOHANG);
        if (res == pid) {
            finished = true;
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    if (!finished) {
        result.timed_out = true;
        result.error_message = "Execution timed out after " + std::to_string(options.timeout_ms) + " ms";
        kill(pid, SIGKILL);
        waitpid(pid, &status, 0);
    } else {
        if (WIFEXITED(status)) {
            result.exit_code = WEXITSTATUS(status);
            result.success = (result.exit_code == 0);
        } else if (WIFSIGNALED(status)) {
            result.exit_code = -1;
            result.error_message = "Process terminated by signal: " + std::to_string(WTERMSIG(status));
        }
    }

    // Read stdout
    char buffer[1024];
    ssize_t bytes_read;
    while ((bytes_read = read(out_pipe[0], buffer, sizeof(buffer) - 1)) > 0) {
        buffer[bytes_read] = '\0';
        result.stdout_output += buffer;
    }
    close(out_pipe[0]);

    // Read stderr
    while ((bytes_read = read(err_pipe[0], buffer, sizeof(buffer) - 1)) > 0) {
        buffer[bytes_read] = '\0';
        result.stderr_output += buffer;
    }
    close(err_pipe[0]);

    auto end_time = std::chrono::high_resolution_clock::now();
    result.execution_time_ms = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time).count();

    return result;
}

#endif

} // namespace native_sandbox
