import ast
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class PythonParser(ast.NodeVisitor):
    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_code = source_code
        self.classes = []

    def parse(self) -> List[Dict[str, Any]]:
        try:
            tree = ast.parse(self.source_code)
            self.visit(tree)
        except Exception as e:
            logger.error(f"Failed to parse Python file {self.file_path}: {e}")
        return self.classes

    def visit_ClassDef(self, node: ast.ClassDef):
        class_name = node.name
        
        # Get decorators (annotations)
        class_annotations = []
        for dec in node.decorator_list:
            # Simple representation of decorator names
            if isinstance(dec, ast.Name):
                class_annotations.append(f"@{dec.id}")
            elif isinstance(dec, ast.Attribute) and isinstance(dec.value, ast.Name):
                class_annotations.append(f"@{dec.value.id}.{dec.attr}")
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    class_annotations.append(f"@{dec.func.id}()")
                elif isinstance(dec.func, ast.Attribute) and isinstance(dec.func.value, ast.Name):
                    class_annotations.append(f"@{dec.func.value.id}.{dec.func.attr}()")

        # Parse body for methods and fields
        methods = []
        dependencies = []
        
        # Look for dependencies in class-level annotations or __init__
        init_node = None
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                init_node = item
                break

        # Check __init__ arguments for dependencies
        if init_node:
            # init_node.args.args contains arguments
            # We skip 'self'
            for arg in init_node.args.args:
                if arg.arg == 'self':
                    continue
                
                param_type = "Any"
                if arg.annotation:
                    param_type = self._get_annotation_string(arg.annotation)
                
                category = "service"
                lower_type = param_type.lower()
                lower_name = arg.arg.lower()
                if "cache" in lower_type or "redis" in lower_type or "cache" in lower_name:
                    category = "cache"
                elif "repo" in lower_type or "repo" in lower_name:
                    category = "repository"
                elif "producer" in lower_type or "consumer" in lower_type or "mq" in lower_type or "kafka" in lower_type or "mq" in lower_name:
                    category = "message_queue"
                elif "client" in lower_type or "http" in lower_type or "client" in lower_name:
                    category = "http_client"
                elif "util" in lower_type or "helper" in lower_type or "util" in lower_name or "helper" in lower_name:
                    category = "utility"

                dependencies.append({
                    "field_name": arg.arg,
                    "type": param_type,
                    "category": category,
                    "mock_strategy": "MagicMock",
                    "annotations": []
                })

        # Process all methods
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name == "__init__":
                    continue
                
                # Visibility
                if item.name.startswith("__"):
                    visibility = "private"
                elif item.name.startswith("_"):
                    visibility = "protected"
                else:
                    visibility = "public"

                # Return type
                return_type = "Any"
                if item.returns:
                    return_type = self._get_annotation_string(item.returns)

                # Parameters
                params = []
                for arg in item.args.args:
                    if arg.arg == 'self':
                        continue
                    p_type = "Any"
                    if arg.annotation:
                        p_type = self._get_annotation_string(arg.annotation)
                    params.append({
                        "name": arg.arg,
                        "type": p_type
                    })

                # Decorators
                method_decorators = []
                for dec in item.decorator_list:
                    if isinstance(dec, ast.Name):
                        method_decorators.append(f"@{dec.id}")
                    elif isinstance(dec, ast.Attribute) and isinstance(dec.value, ast.Name):
                        method_decorators.append(f"@{dec.value.id}.{dec.attr}")
                    elif isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Name):
                            method_decorators.append(f"@{dec.func.id}()")

                # Exceptions (raise statements)
                exceptions = []
                for subnode in ast.walk(item):
                    if isinstance(subnode, ast.Raise):
                        if subnode.exc:
                            if isinstance(subnode.exc, ast.Call) and isinstance(subnode.exc.func, ast.Name):
                                exceptions.append(subnode.exc.func.id)
                            elif isinstance(subnode.exc, ast.Name):
                                exceptions.append(subnode.exc.id)

                # Cyclomatic complexity approximation
                complexity = 1
                for subnode in ast.walk(item):
                    if isinstance(subnode, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With)):
                        complexity += 1
                    elif isinstance(subnode, ast.BoolOp):
                        complexity += len(subnode.values) - 1

                # Priority
                priority = "LOW"
                if visibility == "public":
                    if complexity > 3 or len(dependencies) > 1:
                        priority = "HIGH"
                    else:
                        priority = "MEDIUM"

                methods.append({
                    "name": item.name,
                    "visibility": visibility,
                    "params": params,
                    "return_type": return_type,
                    "throws": list(set(exceptions)),
                    "annotations": method_decorators,
                    "complexity": complexity,
                    "priority": priority
                })

        self.classes.append({
            "class_name": class_name,
            "package": "",  # Python uses modules, package empty or resolved by file path
            "file_path": self.file_path,
            "annotations": class_annotations,
            "methods": methods,
            "dependencies": dependencies
        })

    def _get_annotation_string(self, node: ast.AST) -> str:
        """
        Convert an AST annotation node to its string representation.
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            val = self._get_annotation_string(node.value)
            return f"{val}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            val = self._get_annotation_string(node.value)
            slice_val = self._get_annotation_string(node.slice)
            return f"{val}[{slice_val}]"
        elif isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Tuple):
            return ", ".join(self._get_annotation_string(e) for e in node.elts)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left = self._get_annotation_string(node.left)
            right = self._get_annotation_string(node.right)
            return f"{left} | {right}"
        return "Any"
