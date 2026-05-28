import javalang
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class JavaParser:
    @staticmethod
    def parse_file(file_path: str, source_code: str) -> Optional[Dict[str, Any]]:
        """
        Parse Java source code and extract structural information.
        """
        try:
            tree = javalang.parse.parse(source_code)
        except Exception as e:
            logger.error(f"Failed to parse Java file {file_path}: {e}")
            return None

        # Get package name
        package_name = tree.package.name if tree.package else ""

        # Find class declarations (usually just one primary public class per file)
        class_node = None
        for path, node in tree.filter(javalang.tree.ClassDeclaration):
            # We focus on the main class matching/similar to file name
            class_node = node
            break

        if not class_node:
            return None

        class_name = class_node.name

        # Parse Class Annotations
        class_annotations = []
        for ann in class_node.annotations:
            class_annotations.append(f"@{ann.name}")

        # Parse Fields (potential dependencies)
        dependencies = []
        for _, field_decl in class_node.filter(javalang.tree.FieldDeclaration):
            field_type = field_decl.type.name if field_decl.type else "Unknown"
            
            # Check for generic types, e.g. List<String> or Repository<Order>
            if field_decl.type and hasattr(field_decl.type, 'arguments') and field_decl.type.arguments:
                args = []
                for arg in field_decl.type.arguments:
                    if arg.type:
                        args.append(arg.type.name)
                if args:
                    field_type = f"{field_type}<{', '.join(args)}>"
            
            field_annotations = [f"@{ann.name}" for ann in field_decl.annotations]
            
            # Determine mock strategy based on annotations or type
            mock_strategy = "Mock"
            if "@Autowired" in field_annotations or "@Inject" in field_annotations or "@Resource" in field_annotations:
                mock_strategy = "MockBean"
            elif "@MockBean" in field_annotations:
                mock_strategy = "MockBean"
            elif "@Spy" in field_annotations:
                mock_strategy = "Spy"

            category = "service"
            lower_type = field_type.lower()
            if "cache" in lower_type or "redis" in lower_type:
                category = "cache"
            elif "repository" in lower_type or "repo" in lower_type:
                category = "repository"
            elif "template" in lower_type or "producer" in lower_type or "publisher" in lower_type or "mq" in lower_type or "kafka" in lower_type:
                category = "message_queue"
            elif "client" in lower_type or "http" in lower_type or "feign" in lower_type:
                category = "http_client"
            elif "util" in lower_type or "helper" in lower_type:
                category = "utility"

            for decl in field_decl.declarators:
                dependencies.append({
                    "field_name": decl.name,
                    "type": field_type,
                    "category": category,
                    "mock_strategy": mock_strategy,
                    "annotations": field_annotations
                })

        # Parse Methods
        methods = []
        for _, method_decl in class_node.filter(javalang.tree.MethodDeclaration):
            # Method Name
            method_name = method_decl.name
            
            # Visibility
            visibility = "package-private"
            if "public" in method_decl.modifiers:
                visibility = "public"
            elif "private" in method_decl.modifiers:
                visibility = "private"
            elif "protected" in method_decl.modifiers:
                visibility = "protected"
                
            # Return Type
            return_type = "void"
            if method_decl.return_type:
                return_type = method_decl.return_type.name
                if hasattr(method_decl.return_type, 'arguments') and method_decl.return_type.arguments:
                    args = [arg.type.name for arg in method_decl.return_type.arguments if arg.type]
                    if args:
                        return_type = f"{return_type}<{', '.join(args)}>"

            # Parameters
            params = []
            for param in method_decl.parameters:
                param_type = param.type.name if param.type else "Unknown"
                if param.type and hasattr(param.type, 'arguments') and param.type.arguments:
                    args = [arg.type.name for arg in param.type.arguments if arg.type]
                    if args:
                        param_type = f"{param_type}<{', '.join(args)}>"
                params.append({
                    "name": param.name,
                    "type": param_type
                })

            # Exceptions (throws)
            throws = list(method_decl.throws) if method_decl.throws else []

            # Annotations
            annotations = [f"@{ann.name}" for ann in method_decl.annotations]

            # Calculate cyclomatic complexity approximation
            complexity = 1
            # Filter statements that increase cyclomatic complexity: If, For, While, Switch, Catch
            for _, stmt in method_decl.filter(javalang.tree.IfStatement):
                complexity += 1
            for _, stmt in method_decl.filter(javalang.tree.ForStatement):
                complexity += 1
            for _, stmt in method_decl.filter(javalang.tree.WhileStatement):
                complexity += 1
            for _, stmt in method_decl.filter(javalang.tree.DoStatement):
                complexity += 1
            for _, stmt in method_decl.filter(javalang.tree.CatchClause):
                complexity += 1
            for _, stmt in method_decl.filter(javalang.tree.SwitchStatementCase):
                complexity += 1

            # Estimate priority
            priority = "LOW"
            if visibility == "public":
                if complexity > 4 or len(dependencies) > 2:
                    priority = "HIGH"
                else:
                    priority = "MEDIUM"

            methods.append({
                "name": method_name,
                "visibility": visibility,
                "params": params,
                "return_type": return_type,
                "throws": throws,
                "annotations": annotations,
                "complexity": complexity,
                "priority": priority
            })

        return {
            "class_name": class_name,
            "package": package_name,
            "file_path": file_path,
            "annotations": class_annotations,
            "methods": methods,
            "dependencies": dependencies
        }
