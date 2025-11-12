import ast
import json
import sys
import io
import traceback
import types
from typing import Dict, List, Any, Tuple, Optional
from cerebras_ai import _call_cerebras_ai_chat


class TestGenerator:
    """Generates and executes unit tests for Python source code."""
    
    def __init__(self, source_code: str):
        self.source_code = source_code
        self.module = None
        self.functions = []
        self.classes = []
        
    def parse_source_code(self) -> Dict[str, Any]:
        """Parse source code to extract functions and classes."""
        try:
            tree = ast.parse(self.source_code)
            functions = []
            classes = []
            
            # Only parse top-level functions and classes (not nested ones)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.FunctionDef):
                    # Get function signature
                    args = [arg.arg for arg in node.args.args]
                    functions.append({
                        'name': node.name,
                        'args': args,
                        'lineno': node.lineno
                    })
                elif isinstance(node, ast.ClassDef):
                    methods = []
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            args = [arg.arg for arg in item.args.args if arg.arg != 'self']
                            methods.append({
                                'name': item.name,
                                'args': args,
                                'lineno': item.lineno
                            })
                    classes.append({
                        'name': node.name,
                        'methods': methods,
                        'lineno': node.lineno
                    })
            
            self.functions = functions
            self.classes = classes
            
            return {
                'functions': functions,
                'classes': classes
            }
        except SyntaxError as e:
            raise ValueError(f"Invalid Python syntax: {str(e)}")
    
    def execute_source_code(self) -> types.ModuleType:
        """Execute source code in a new module namespace."""
        try:
            # Create a new module
            module = types.ModuleType('test_module')
            # Execute source code in module namespace
            exec(self.source_code, module.__dict__)
            self.module = module
            return module
        except Exception as e:
            raise RuntimeError(f"Failed to execute source code: {str(e)}")
    
    def generate_test_cases_ai(self, function_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate test cases using AI for a given function."""
        prompt = f"""Generate 3-5 test cases for the following Python function:

Function name: {function_info['name']}
Arguments: {function_info['args']}

Source code context:
{self.source_code}

For each test case, provide:
1. Input values as a list (match the function arguments)
2. Expected behavior or edge cases to test

Return the test cases as a JSON array where each test case has:
- "inputs": array of input values
- "description": brief description of what this test case checks

Example format:
[
  {{"inputs": [1, 2], "description": "Test with positive integers"}},
  {{"inputs": [0, 0], "description": "Test with zeros"}},
  {{"inputs": [-1, 5], "description": "Test with negative number"}}
]

Only return the JSON array, nothing else."""
        
        try:
            response = _call_cerebras_ai_chat(prompt, max_tokens=1000)
            # Try to extract JSON from response
            # Remove markdown code blocks if present
            response = response.strip()
            if response.startswith('```'):
                response = response.split('```')[1]
                if response.startswith('json'):
                    response = response[4:]
                response = response.strip()
            elif response.startswith('```json'):
                response = response[7:].strip().rstrip('```').strip()
            
            test_cases = json.loads(response)
            return test_cases
        except Exception as e:
            # Fallback to heuristic-based generation
            return self.generate_test_cases_heuristic(function_info)
    
    def generate_test_cases_heuristic(self, function_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate test cases using heuristics when AI is unavailable."""
        args = function_info['args']
        test_cases = []
        
        # Generate basic test cases based on number of arguments
        if len(args) == 0:
            test_cases.append({
                "inputs": [],
                "description": "Test function with no arguments"
            })
        elif len(args) == 1:
            test_cases.extend([
                {"inputs": [1], "description": "Test with positive integer"},
                {"inputs": [0], "description": "Test with zero"},
                {"inputs": [-1], "description": "Test with negative integer"},
                {"inputs": ["test"], "description": "Test with string"},
            ])
        elif len(args) == 2:
            test_cases.extend([
                {"inputs": [1, 2], "description": "Test with two positive integers"},
                {"inputs": [0, 0], "description": "Test with two zeros"},
                {"inputs": [-1, 5], "description": "Test with mixed signs"},
                {"inputs": ["a", "b"], "description": "Test with two strings"},
            ])
        else:
            # For functions with more arguments, use default values
            default_values = [0] * len(args)
            test_cases.append({
                "inputs": default_values,
                "description": f"Test with default values for {len(args)} arguments"
            })
        
        return test_cases
    
    def run_test_case(self, function_name: str, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single test case and capture results."""
        if not self.module:
            self.execute_source_code()
        
        inputs = test_case.get('inputs', [])
        description = test_case.get('description', 'No description')
        
        # Capture stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        test_passed = False
        result_value = None
        error_message = None
        
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            
            # Get the function from module
            if not hasattr(self.module, function_name):
                raise AttributeError(f"Function '{function_name}' not found in source code")
            
            func = getattr(self.module, function_name)
            
            # Execute the function
            result_value = func(*inputs)
            
            # If no exception was raised, test passed (basic execution test)
            test_passed = True
            
        except Exception as e:
            error_message = str(e)
            test_passed = False
            # Store the exception info
            result_value = {
                "error": error_message,
                "traceback": traceback.format_exc()
            }
        
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        
        # Format result value for JSON serialization
        completion_result_values = self._format_result(result_value)
        
        return {
            "testDescription": description,
            "testCases": inputs,
            "isTestPassed": test_passed,
            "completionResultValues": completion_result_values,
            "error": error_message
        }
    
    def _format_result(self, result: Any) -> Any:
        """Format result value to be JSON serializable."""
        if result is None:
            return None
        
        # Handle basic types
        if isinstance(result, (int, float, str, bool)):
            return result
        
        # Handle collections
        if isinstance(result, (list, tuple)):
            return [self._format_result(item) for item in result]
        
        if isinstance(result, dict):
            return {str(k): self._format_result(v) for k, v in result.items()}
        
        # Handle sets
        if isinstance(result, set):
            return list(result)
        
        # For other types, convert to string representation
        try:
            # Try to get a meaningful representation
            if hasattr(result, '__dict__'):
                return str(result)
            return str(result)
        except:
            return "<unserializable>"
    
    def generate_and_run_tests(self, use_ai: bool = True) -> List[Dict[str, Any]]:
        """Main method to generate and run all tests."""
        # Parse source code
        parse_result = self.parse_source_code()
        
        # Execute source code
        self.execute_source_code()
        
        all_test_results = []
        
        # Generate tests for functions
        for func_info in self.functions:
            func_name = func_info['name']
            
            # Skip private functions (starting with _) unless they're __init__ or special methods
            if func_name.startswith('_') and not func_name.startswith('__'):
                continue
            
            # Generate test cases
            if use_ai:
                try:
                    test_cases = self.generate_test_cases_ai(func_info)
                except:
                    test_cases = self.generate_test_cases_heuristic(func_info)
            else:
                test_cases = self.generate_test_cases_heuristic(func_info)
            
            # Run each test case
            for test_case in test_cases:
                try:
                    test_result = self.run_test_case(func_name, test_case)
                    # Remove error field if test passed
                    if test_result['isTestPassed']:
                        test_result.pop('error', None)
                    all_test_results.append(test_result)
                except Exception as e:
                    # If test setup fails, create a failure result
                    all_test_results.append({
                        "testDescription": f"Test setup failed for {func_name}",
                        "testCases": [],
                        "isTestPassed": False,
                        "completionResultValues": None,
                        "error": str(e)
                    })
        
        # Generate tests for class methods
        for class_info in self.classes:
            class_name = class_info['name']
            
            # Try to instantiate the class
            try:
                if hasattr(self.module, class_name):
                    cls = getattr(self.module, class_name)
                    # Try to create an instance (handle __init__ parameters)
                    instance = None
                    try:
                        instance = cls()
                    except:
                        # If no-arg constructor fails, we'll skip instance methods
                        pass
                    
                    for method_info in class_info['methods']:
                        method_name = method_info['name']
                        
                        # Skip private methods
                        if method_name.startswith('_') and not method_name.startswith('__'):
                            continue
                        
                        if instance is None and method_name != '__init__':
                            continue
                        
                        # Generate test cases
                        if use_ai:
                            try:
                                test_cases = self.generate_test_cases_ai(method_info)
                            except:
                                test_cases = self.generate_test_cases_heuristic(method_info)
                        else:
                            test_cases = self.generate_test_cases_heuristic(method_info)
                        
                        # Run each test case
                        for test_case in test_cases:
                            try:
                                if method_name == '__init__':
                                    # For __init__, test case inputs are used to create instance
                                    inputs = test_case.get('inputs', [])
                                    try:
                                        instance = cls(*inputs)
                                        test_result = {
                                            "testDescription": f"Test {class_name}.__init__: {test_case.get('description', '')}",
                                            "testCases": inputs,
                                            "isTestPassed": True,
                                            "completionResultValues": None
                                        }
                                    except Exception as e:
                                        test_result = {
                                            "testDescription": f"Test {class_name}.__init__: {test_case.get('description', '')}",
                                            "testCases": inputs,
                                            "isTestPassed": False,
                                            "completionResultValues": None,
                                            "error": str(e)
                                        }
                                else:
                                    # For regular methods, call on instance
                                    inputs = test_case.get('inputs', [])
                                    method = getattr(instance, method_name)
                                    result_value = method(*inputs)
                                    
                                    test_result = {
                                        "testDescription": f"Test {class_name}.{method_name}: {test_case.get('description', '')}",
                                        "testCases": inputs,
                                        "isTestPassed": True,
                                        "completionResultValues": self._format_result(result_value)
                                    }
                                
                                all_test_results.append(test_result)
                            except Exception as e:
                                all_test_results.append({
                                    "testDescription": f"Test {class_name}.{method_name}: {test_case.get('description', '')}",
                                    "testCases": test_case.get('inputs', []),
                                    "isTestPassed": False,
                                    "completionResultValues": None,
                                    "error": str(e)
                                })
            except Exception as e:
                # If class instantiation fails, add error result
                all_test_results.append({
                    "testDescription": f"Failed to test class {class_name}",
                    "testCases": [],
                    "isTestPassed": False,
                    "completionResultValues": None,
                    "error": str(e)
                })
        
        return all_test_results


def generate_and_run_unit_tests(source_code: str, use_ai: bool = True) -> str:
    """
    Main entry point for generating and running unit tests.
    
    Args:
        source_code: Python source code string
        use_ai: Whether to use AI for test case generation (default: True)
    
    Returns:
        JSON string containing array of test results
    """
    try:
        generator = TestGenerator(source_code)
        results = generator.generate_and_run_tests(use_ai=use_ai)
        
        # Clean up results (remove error field if present and test passed)
        cleaned_results = []
        for result in results:
            cleaned_result = {
                "testDescription": result.get("testDescription", ""),
                "testCases": result.get("testCases", []),
                "isTestPassed": result.get("isTestPassed", False),
                "completionResultValues": result.get("completionResultValues")
            }
            cleaned_results.append(cleaned_result)
        
        return json.dumps(cleaned_results, indent=2)
    except Exception as e:
        # Return error result
        error_result = [{
            "testDescription": f"Failed to generate tests: {str(e)}",
            "testCases": [],
            "isTestPassed": False,
            "completionResultValues": None
        }]
        return json.dumps(error_result, indent=2)

