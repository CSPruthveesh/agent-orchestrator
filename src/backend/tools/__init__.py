import os
import sys
from pathlib import Path

# Register MSYS2 runtime DLL directory on Windows if present
if sys.platform == "win32":
    msys2_bin = "C:\\msys64\\ucrt64\\bin"
    if os.path.exists(msys2_bin):
        try:
            os.add_dll_directory(msys2_bin)
        except Exception:
            pass

# Add current tools directory to sys.path
tools_dir = Path(__file__).resolve().parent
if str(tools_dir) not in sys.path:
    sys.path.insert(0, str(tools_dir))

try:
    import native_sandbox_cpp
    execute_sandboxed_code = native_sandbox_cpp.execute_sandboxed_code
except ImportError:
    execute_sandboxed_code = None
