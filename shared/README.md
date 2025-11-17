# Shared Module

This module provides common utilities used across all Impactra services.

## Contents

### `file_worker.py`
File and task management utilities:

- **`find_task_folder(task_id, max_attempts=5, base_delay=1.0)`**: Locates task folder with exponential backoff retry logic
- **`read_subtasks(task_id)`**: Reads and validates subtask JSON files from a task folder
- **`get_subtasks_for_processing(task_id)`**: Retrieves subtasks ready for processing
- **`save_subtask_source_code(source_code, task_id, subtask_index)`**: Saves generated source code with auto-detected file extension
- **`detect_file_extension(source_code)`**: Detects programming language from source code content
- **`extract_order_number(filename)`**: Extracts ordering number from subtask filenames

### Constants
- **`DATA_BASE_PATH`**: Base path for task data volume (default: `/data/tasks`)
- **`RESULT_ARTIFACTS_FOLDER`**: Subfolder name for result artifacts (default: `result artifacts`)
- **`LANGUAGE_PATTERNS`**: Dictionary of regex patterns for language detection

## Usage

### Basic Import (from any service)

```python
import sys
from pathlib import Path

# Add parent directory to path to import shared module
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import get_subtasks_for_processing, save_subtask_source_code
```

Or import specific functions:

```python
from shared.file_worker import (
    find_task_folder,
    read_subtasks,
    detect_file_extension,
    save_subtask_source_code
)
```

### Examples

**Read subtasks for a task:**
```python
from shared import get_subtasks_for_processing

subtasks = get_subtasks_for_processing("task-12345")
for task in subtasks:
    print(f"Task: {task['taskName']}")
    print(f"Description: {task['taskDescription']}")
```

**Save generated source code:**
```python
from shared import save_subtask_source_code

file_path = save_subtask_source_code(
    source_code=my_generated_code,
    task_id="task-12345",
    subtask_index=1
)
```

**Detect file extension:**
```python
from shared import detect_file_extension

extension = detect_file_extension(source_code)  # Returns 'py', 'js', 'cs', etc.
```

## Services Using This Module

- `BusinessAnalyst`: Task analysis and splitting
- `Programmer`: Code generation
- `CodeRunner`: Code execution
- `Tester`: Code testing

## Adding New Utilities

1. Add functions to `file_worker.py`
2. Export them in `__init__.py` under `__all__`
3. Import and use in services via the shared module

## Logging

All functions use Python's standard `logging` module. Enable debug logging to see detailed operations:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```
