import os
import sys
import pytest
from pathlib import Path

# On Windows with MSYS2 MinGW GCC, register MSYS2 bin directory for C++ runtime DLL resolution
if sys.platform == "win32":
    msys2_bin = "C:\\msys64\\ucrt64\\bin"
    if os.path.exists(msys2_bin):
        try:
            os.add_dll_directory(msys2_bin)
        except Exception:
            pass

# Add src/backend/tools to sys.path so native_sandbox_cpp can be imported
tools_dir = Path(__file__).resolve().parent.parent.parent / "src" / "backend" / "tools"
sys.path.insert(0, str(tools_dir))


def test_native_sandbox_pybind_import():
    """
    Asserts that native_sandbox_cpp C++ pybind module imports cleanly.
    """
    import native_sandbox_cpp
    assert hasattr(native_sandbox_cpp, "execute_sandboxed_code")


def test_native_sandbox_code_execution():
    """
    Asserts command execution via C++ native sandbox pybind binding.
    """
    import native_sandbox_cpp
    res = native_sandbox_cpp.execute_sandboxed_code("whoami", timeout_ms=3000, memory_limit_mb=256)
    assert isinstance(res, dict)
    assert res["success"] is True
    assert res["exit_code"] == 0
    assert res["timed_out"] is False
    assert len(res["stdout_output"]) > 0


def test_native_sandbox_timeout_enforcement():
    """
    Asserts timeout handling via C++ native sandbox pybind binding.
    """
    import native_sandbox_cpp
    res = native_sandbox_cpp.execute_sandboxed_code(
        "powershell -Command Start-Sleep -Seconds 3",
        timeout_ms=500,
        memory_limit_mb=256
    )
    assert res["timed_out"] is True
    assert res["success"] is False
