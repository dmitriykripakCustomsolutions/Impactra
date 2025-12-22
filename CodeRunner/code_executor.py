import sys
import io
import os
import shutil
import tempfile
import subprocess
from contextlib import redirect_stdout, redirect_stderr
import re
import traceback
from pathlib import Path
import logging
import json
from repo_worker import _save_source_to_repo 

# Add shared module to path for both local and Docker environments
shared_paths = [
    Path(__file__).parent.parent,  # Local development: ../shared
    Path('/app'),  # Docker: /app/shared
]

for path in shared_paths:
    if path.exists():
        sys.path.insert(0, str(path))
        break

from shared import find_task_folder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("__main__")

# Constants
RESULT_ARTIFACTS_FOLDER = "Result artifacts"

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


def execute_code_safely(code_snippet, result_dir: str | Path = None, attachments: list[Path] | None = None, pip_install: bool = True, install_timeout: int = 120):
    """
    Execute the code snippet in an isolated temporary working directory.

    - `result_dir` (optional): if provided, any generated artifact files (images, charts)
      found in the temp directory will be copied into this directory.
    - `pip_install`: if True, attempts to pip install detected imports that are missing.
    - Returns a dict with keys: compiled, output, error, sourceCode, artifacts
    """
    sanitized = sanitize_code(code_snippet)

    # Normalize attachments parameter to a list of Path objects
    normalized_attachments = []
    if attachments:
        # If a single path string/Path passed, wrap it
        if isinstance(attachments, (str, Path)):
            attachments_iter = [attachments]
        else:
            attachments_iter = attachments

        for a in attachments_iter:
            try:
                normalized_attachments.append(Path(a))
            except Exception:
                # write to stderr_buffer later (we don't have it yet); for now, skip invalid
                continue
    attachments = normalized_attachments

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
                # Copy provided attachments into the temp dir and prepare attachments mapping
                attachments_mapping = {}
                if attachments:
                    for attach in attachments:
                        try:
                            p = Path(attach)
                            if p.exists() and p.is_file():
                                dest = Path(tmpdir) / p.name
                                shutil.copy2(p, dest)
                                attachments_mapping[p.name] = str(dest)
                            else:
                                stderr_buffer.write(f"Attachment not found or not a file: {attach}\n")
                        except Exception as ae:
                            try:
                                stderr_buffer.write(f"Attachment copy failed for {attach}: {ae}\n")
                            except Exception:
                                pass

                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    # provide a minimal globals namespace but expose attachments mapping
                    exec_globals = {"__name__": "__main__", "attachments": attachments_mapping}
                    exec(sanitized, exec_globals, exec_globals)
            except Exception as e:
                # capture runtime error with full traceback so caller can see origin
                tb = traceback.format_exc()
                error_message = f"Runtime Error: {str(e)}\n{tb}"

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
                    # Also include any attachments that were copied into tmpdir
                    if attachments:
                        for attach in attachments:
                            try:
                                p = Path(attach)
                                local = result_path / p.name
                                if local.exists():
                                    # already copied by above loop
                                    if str(local) not in artifacts:
                                        artifacts.append(str(local))
                                else:
                                    # copy original attachment into result path
                                    src = Path(tmpdir) / p.name
                                    if src.exists():
                                        dst = result_path / src.name
                                        shutil.copy2(src, dst)
                                        artifacts.append(str(dst))
                            except Exception as ae:
                                stderr_buffer.write(f"Attachment final copy failed for {attach}: {ae}\n")
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


def get_source_code_files(task_id: str):
    """
    Find and read all source code files from the task's Result artifacts folder.
    Returns a list of tuples: (filename, source_code)
    """
    try:
        task_folder = find_task_folder(task_id)
        result_artifacts_path = Path(task_folder) / RESULT_ARTIFACTS_FOLDER
        # We prefer files placed inside the `result artifacts` folder, but some workflows
        # put attachments/source files directly in the parent task folder. Search both
        # locations and use the first one that contains matching files.
        search_locations = [result_artifacts_path, Path(task_folder)]
        found_files = []
        found_in = None
        for loc in search_locations:
            if not loc.exists():
                continue
            candidate_files = sorted(
                loc.glob("Whole source code_subtask_*"),
                key=lambda f: extract_order_from_filename(f.name)
            )
            if candidate_files:
                found_files = candidate_files
                found_in = loc
                break

        if not found_files:
            logger.warning(f"No source code files found in: {result_artifacts_path} or {task_folder}")
            return []
        
        # Find all source code files matching pattern: Whole source code_subtask_<number>.<extension>
        source_files = sorted(
            result_artifacts_path.glob("Whole source code_subtask_*"),
            key=lambda f: extract_order_from_filename(f.name)
        )
        
        if not source_files:
            logger.warning(f"No source code files found in: {result_artifacts_path}")
            return []
        
        logger.info(f"Found {len(found_files)} source code files in {found_in}: {[f.name for f in found_files]}")

        # Read all files
        files_with_content = []
        for file_path in found_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    files_with_content.append((file_path.name, content))
                    logger.info(f"Loaded source code from: {file_path.name}")
            except Exception as e:
                logger.error(f"Failed to read file {file_path.name}: {e}")
                raise
        
        return files_with_content
        
    except FileNotFoundError as e:
        logger.error(f"Task folder not found for taskId {task_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error retrieving source code files for taskId {task_id}: {e}")
        raise

def extract_order_from_filename(filename: str) -> int:
    if not filename:
        return float('inf')

    fname = str(filename)
    # Look specifically for 'subtask_<digits>' and capture the digits right after the suffix
    match = re.search(r'subtask_(\d+)', fname)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return float('inf')

def execute_all_subtask_code(task_id: str):
    """
    Execute all source code files for a task and return results.
    """
    try:
        # Get all source code files
        source_files = get_source_code_files(task_id)

        # Determine the task folder and Result artifacts path so we can write per-subtask results
        task_folder = find_task_folder(task_id)
        result_artifacts_path = Path(task_folder) / RESULT_ARTIFACTS_FOLDER
        
        if not source_files:
            return {
                "taskId": task_id,
                "results": [],
                "status": "no_code_files_found"
            }
        
        # Execute each file and collect results
        execution_results = []
        for filename, source_code in source_files:
            logger.info(f"Executing {filename}...")
            try:
                # derive subtask index for matching requirement files
                try:
                    subtask_index = extract_order_from_filename(filename)
                except Exception:
                    subtask_index = None

                # Look for requirement JSON file in the task folder matching *subtask_<index>.json
                attachments_to_pass = []
                if subtask_index is not None:
                    try:
                        pattern = f"*subtask_{subtask_index}.json"
                        req_files = list(Path(task_folder).glob(pattern))
                        if req_files:
                            # pick first matching requirement file
                            req_path = req_files[0]
                            try:
                                with open(req_path, 'r', encoding='utf-8') as rf:
                                    req_json = json.load(rf)
                                attach_name = req_json.get('attachment')
                                if attach_name:
                                    attach_path = Path(task_folder) / attach_name
                                    if attach_path.exists():
                                        attachments_to_pass.append(attach_path)
                                    else:
                                        logger.warning(f"Attachment listed in {req_path} not found: {attach_path}")
                            except Exception as e:
                                logger.warning(f"Failed to read requirement file {req_path}: {e}")
                    except Exception:
                        pass

                result = execute_code_safely(source_code, result_dir=result_artifacts_path, attachments=attachments_to_pass)
                execution_results.append({
                    "subtask": filename,
                    "compiled": result.get("compiled", False),
                    "output": result.get("output", ""),
                    "error": result.get("error", ""),
                    "sourceCode": result.get("sourceCode", "")
                })
                # Attempt to derive subtask index from filename; fall back to enumerating
                try:
                    subtask_index = extract_order_from_filename(filename)
                    if not isinstance(subtask_index, int):
                        raise ValueError
                except Exception:
                    # fallback: use current length of execution_results - 1 as index
                    subtask_index = len(execution_results) - 1

                # Ensure Result artifacts folder exists
                try:
                    result_artifacts_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    logger.warning(f"Could not create Result artifacts folder {result_artifacts_path}: {e}")

                # Write the per-subtask result to JSON file
                try:
                    result_item = execution_results[-1]
                    output_file = result_artifacts_path / f"Run result_subtask_{subtask_index}.json"
                    with open(output_file, 'w', encoding='utf-8') as out_f:
                        json.dump(result_item, out_f, ensure_ascii=False, indent=2)
                    logger.info(f"Saved run result to {output_file}")
                except Exception as e:
                    logger.error(f"Failed to write run result for {filename}: {e}")

                # If execution produced no error, save successful source to repository
                try:
                    last_result = execution_results[-1]
                    err = last_result.get("error", "")
                    if not err:
                        # Determine a reasonable filename to save (use original filename)
                        save_filename = filename
                        # Save the source into the repository (best-effort)
                        try:
                            _save_source_to_repo(task_id, save_filename, last_result.get("sourceCode", ""))
                        except Exception as se:
                            logger.warning(f"Failed to save successful source to repo: {se}")
                except Exception as e:
                    logger.error(f"Failed to write run result for {filename}: {e}")
                logger.info(f"✓ Completed execution of {filename}")
            except Exception as e:
                logger.error(f"Failed to execute {filename}: {e}")
                execution_results.append({
                    "subtask": filename,
                    "compiled": False,
                    "output": "",
                    "error": str(e),
                    "sourceCode": source_code
                })
        
        return {
            "taskId": task_id,
            "results": execution_results,
            "status": "success",
            "totalSubtasks": len(source_files),
            "successfulExecutions": sum(1 for r in execution_results if r["compiled"])
        }
        
    except Exception as e:
        logger.error(f"Error executing subtasks for taskId {task_id}: {e}")
        return {
            "taskId": task_id,
            "results": [],
            "status": "error",
            "error": str(e)
        }
