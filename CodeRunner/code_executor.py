import sys
import io
import os
import shutil
import tempfile
import subprocess
from contextlib import redirect_stdout, redirect_stderr
import re
from pathlib import Path


def _detect_imports(code: str):
    """Return a set of top-level module names detected in import statements."""
    modules = set()
    # match: import pkg, import pkg as p, from pkg.sub import x
    for m in re.finditer(r'^[ \t]*(?:from|import)\s+([a-zA-Z0-9_\.]+)', code, flags=re.MULTILINE):
        name = m.group(1).split('.')[0]
        modules.add(name)
    return modules


def _ensure_module_available(module_name: str, pip_install: bool = True, timeout: int = 120):
    """Try importing module_name; if missing and pip_install True, attempt to pip install it."""
    try:
        __import__(module_name)
        return True, None
    except Exception as e:
        if not pip_install:
            return False, str(e)
        # Try pip install
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', module_name], check=True, capture_output=True, timeout=timeout)
            # try import again
            __import__(module_name)
            return True, None
        except Exception as pe:
            return False, f"Failed to install/import {module_name}: {pe}"


def execute_code_safely(code_snippet, result_dir: str | Path = None, pip_install: bool = True, install_timeout: int = 120):
    """
    Execute the code snippet in an isolated temporary working directory.

    - `result_dir` (optional): if provided, any generated artifact files (images, charts)
      found in the temp directory will be copied into this directory.
    - `pip_install`: if True, attempts to pip install detected imports that are missing.
    - Returns a dict with keys: compiled, output, error, sourceCode, artifacts
    """
    sanitized = sanitize_code(code_snippet)

    # detect imports and try to ensure modules are available
    missing_modules = {}
    try:
        modules = _detect_imports(sanitized)
        for mod in modules:
            ok, msg = _ensure_module_available(mod, pip_install=pip_install, timeout=install_timeout)
            if not ok:
                missing_modules[mod] = msg
    except Exception as e:
        # detection shouldn't stop execution
        missing_modules['detection_error'] = str(e)

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    compilation_status = True
    execution_output = ""
    error_message = ""
    artifacts = []

    # Prepare temp working directory to capture produced files
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # Set non-interactive matplotlib backend to avoid GUI requirements
            os.environ.setdefault('MPLBACKEND', 'Agg')

            # First try to compile
            try:
                compile(sanitized, '<string>', 'exec')
            except SyntaxError as se:
                compilation_status = False
                error_message = f"Syntax Error: {str(se)}"
                return {
                    "compiled": compilation_status,
                    "output": "",
                    "error": error_message,
                    "sourceCode": sanitized,
                    "artifacts": []
                }

            # If import installation failed for some modules, report and continue (execution may still fail)
            if missing_modules:
                stderr_buffer.write("Missing modules or install errors:\n")
                for k, v in missing_modules.items():
                    stderr_buffer.write(f"{k}: {v}\n")

            # Execute the code
            try:
                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    # provide a minimal globals namespace but allow full imports
                    exec_globals = {"__name__": "__main__"}
                    exec(sanitized, exec_globals, exec_globals)
            except Exception as e:
                # capture runtime error
                error_message = f"Runtime Error: {str(e)}"

            execution_output = stdout_buffer.getvalue()
            # combine stderr buffer and runtime error
            stderr_contents = stderr_buffer.getvalue()
            if stderr_contents:
                if error_message:
                    error_message = stderr_contents + "\n" + error_message
                else:
                    error_message = stderr_contents

            # After execution, collect likely artifact files (images/charts)
            if result_dir is not None:
                try:
                    result_path = Path(result_dir)
                    result_path.mkdir(parents=True, exist_ok=True)
                    # choose extensions commonly used for charts
                    exts = ['.png', '.jpg', '.jpeg', '.svg', '.gif', '.pdf']
                    for f in Path(tmpdir).iterdir():
                        if f.is_file() and f.suffix.lower() in exts:
                            dest = result_path / f.name
                            # avoid overwriting: add suffix if exists
                            if dest.exists():
                                base = dest.stem
                                i = 1
                                while True:
                                    candidate = result_path / f"{base}_{i}{dest.suffix}"
                                    if not candidate.exists():
                                        dest = candidate
                                        break
                                    i += 1
                            shutil.copy2(f, dest)
                            artifacts.append(str(dest))
                except Exception as e:
                    # don't fail on artifact copying
                    error_message = (error_message + "\n" if error_message else "") + f"Artifact copy error: {e}"

        finally:
            os.chdir(orig_cwd)
            stdout_buffer.close()
            stderr_buffer.close()

    return {
        "compiled": compilation_status,
        "output": execution_output,
        "error": error_message,
        "sourceCode": sanitized,
        "artifacts": artifacts
    }


def sanitize_code(raw_code: str) -> str:
    """
    Remove markdown code fences, language specifiers, and unnecessary whitespace from code.
    """
    if raw_code is None:
        return ""

    # Ensure we are working with a str
    if not isinstance(raw_code, str):
        try:
            raw_code = str(raw_code)
        except Exception:
            return ""

    s = raw_code.strip()

    # If the code is wrapped in quotes (single or double), remove matching outer quotes repeatedly
    while len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1].strip()

    # If the string contains literal escape sequences like \\n+    # and no real newlines, decode them
    # This handles cases where the snippet was passed as an escaped literal: "\\\\n"
    if "\\n" in s and "\n" not in s:
        try:
            s = bytes(s, "utf-8").decode("unicode_escape")
        except Exception:
            # If decoding fails, keep the original
            pass

    # Remove leading triple backticks and optional language (e.g., ```python\n)
    s = re.sub(r"^```[ \t]*[a-zA-Z0-9_+\-]*[ \t]*\n?", "", s)
    # Remove trailing triple backticks
    s = re.sub(r"\n?```[ \t]*$", "", s)

    # If any leftover leading/trailing backticks remain (1-3), strip them
    s = re.sub(r"^`{1,3}", "", s)
    s = re.sub(r"`{1,3}$", "", s)

    return s.strip()