import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import sys

# Mock the volume path to use a temporary directory for testing
test_volume_path = None


def setup_test_volume():
    """Create a temporary test volume."""
    global test_volume_path
    test_volume_path = tempfile.mkdtemp()
    print(f"Test volume created at: {test_volume_path}")
    return test_volume_path


def cleanup_test_volume():    
    global test_volume_path
    if test_volume_path and Path(test_volume_path).exists():
        import shutil
        shutil.rmtree(test_volume_path)
        print(f"Test volume cleaned up: {test_volume_path}")


def test_task_storage():
    """Test the task storage functionality."""
    # Setup test environment
    test_vol = setup_test_volume()
    
    # Patch the TASKS_VOLUME_PATH in task_storage module
    with patch('task_storage.TASKS_VOLUME_PATH', test_vol):
        # Import after patching
        from task_storage import save_task_results
        
        # Test data matching the format described
        original_text = "Write a selection sort algorithm that sorts an array of elements in ascending order."
        tasks_data = json.dumps([
            {
                "taskName": "Selection Sort Algorithm",
                "taskDescription": "Write a selection sort algorithm that sorts an array of elements in ascending order by repeatedly finding the minimum element from the unsorted part of the array and putting it at the beginning of the unsorted part."
            },
            {
                "taskName": "Test Selection Sort",
                "taskDescription": "Create comprehensive test cases for the selection sort implementation."
            }
        ])
        
        # Call save_task_results
        result = save_task_results(original=original_text, tasks_result=tasks_data)
        print(f"\nSave result: {json.dumps(result, indent=2)}")
        
        # Verify folder structure
        if result["status"] == "success":
            task_folder = Path(result["folder_path"])
            
            # Check original requirements file
            original_file = task_folder / "Original task requirements.txt"
            assert original_file.exists(), f"Original file not found: {original_file}"
            original_content = original_file.read_text()
            assert original_content == original_text, "Original content mismatch"
            print(f"✓ Original requirements file found and verified")
            
            # Check task files
            task_files = list(task_folder.glob("*.json"))
            assert len(task_files) == 2, f"Expected 2 task files, found {len(task_files)}"
            print(f"✓ Found {len(task_files)} task JSON files")
            
            # Verify task file contents
            for task_file in task_files:
                task_content = json.loads(task_file.read_text())
                print(f"  - {task_file.name}: {task_content.get('taskName', 'Unknown')}")
                assert "taskName" in task_content, f"Missing taskName in {task_file.name}"
                assert "taskDescription" in task_content, f"Missing taskDescription in {task_file.name}"
            
            print(f"\n✓ All tests passed!")
            print(f"✓ Task folder structure verified at: {task_folder}")
        else:
            print(f"✗ Save failed: {result['message']}")
            return False
    
    # Cleanup
    cleanup_test_volume()
    return True


if __name__ == "__main__":
    try:
        success = test_task_storage()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        cleanup_test_volume()
        sys.exit(1)
