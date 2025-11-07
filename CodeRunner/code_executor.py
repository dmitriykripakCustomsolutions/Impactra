import sys
import io
from contextlib import redirect_stdout, redirect_stderr
import re

def execute_code_safely(code_snippet):
    # Sanitize sourceCode before execution
    sanitized = sanitize_code(code_snippet)

    # Create string buffers for stdout and stderr displaying the output and errors
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    
    compilation_status = True
    execution_output = ""
    error_message = ""
    
    try:
        # First try to compile the code to check for syntax errors
        compile(sanitized, '<string>', 'exec')
        
        # If compilation succeeds, execute the code
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            exec(sanitized, {}, {})
            
        execution_output = stdout_buffer.getvalue()
        error_message = stderr_buffer.getvalue()
        
    except SyntaxError as e:
        compilation_status = False
        error_message = f"Syntax Error: {str(e)}"
    except Exception as e:
        compilation_status = True  # Code compiled but failed during execution
        error_message = f"Runtime Error: {str(e)}"
    
    finally:
        stdout_buffer.close()
        stderr_buffer.close()
    
    return {
        "compiled": compilation_status,
        "output": execution_output,
        "error": error_message,
        "sourceCode": sanitized
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

    # If the string contains literal escape sequences like \n and no real newlines, decode them
    # This handles cases where the snippet was passed as an escaped literal: "\n"
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