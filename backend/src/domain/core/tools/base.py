"""
Base tool classes and registry for LLM tool calling.

Tools are CLASSES whose action methods are named with a single leading
underscore (`_propose_refund`). The class introspects those methods and
auto-generates Bedrock `toolSpec` / OpenAI `function` configs from the
signature and docstring — so adding a tool is adding a method, nothing
else. A ToolRegistry holds several tool-class instances and routes a
tool call to whichever class owns it.

This module is pure framework: it depends on nothing in infrastructure.
Concrete tool classes (propose_tools, evidence_tools) receive their
collaborators (an executor, a dispute source) by constructor injection,
typed against domain interfaces.
"""
import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, get_type_hints

from src.shared.logging import get_logger

logger = get_logger(__name__)


class BaseTool(ABC):
    """Base class for all tools."""

    def __init__(self, enabled_tools: list[str] | None = None, **kwargs) -> None:
        """
        Args:
            enabled_tools: Restrict which `_methods` are exposed; None = all.
            **kwargs: Per-turn context / dependencies (e.g. user, case_id).
        """
        self.kwargs = kwargs
        self.enabled_tools = enabled_tools

    @classmethod
    def generate_bedrock_config(cls, enabled_tools: list[str] | None = None) -> dict[str, Any]:
        """Generate a Bedrock toolConfig from this class's `_methods`."""
        tools = []
        methods = inspect.getmembers(cls, predicate=inspect.isfunction)
        for method_name, method in methods:
            if (
                method_name.startswith("_")
                and not method_name.startswith("__")
                and method_name not in ("_generate_method_spec", "_generate_openai_function_spec")
            ):
                tool_name = method_name[1:]
                if enabled_tools is None or tool_name in enabled_tools:
                    tools.append(cls._generate_method_spec(method_name, method))
        return {"tools": tools, "toolChoice": {"auto": {}}}

    @classmethod
    def generate_openai_config(cls, enabled_tools: list[str] | None = None) -> list[dict[str, Any]]:
        """Generate an OpenAI functions config from this class's `_methods`."""
        functions = []
        methods = inspect.getmembers(cls, predicate=inspect.isfunction)
        for method_name, method in methods:
            if method_name.startswith("_") and not method_name.startswith("__"):
                tool_name = method_name[1:]
                if enabled_tools is None or tool_name in enabled_tools:
                    functions.append(cls._generate_openai_function_spec(method_name, method))
        return functions

    @classmethod
    def _generate_method_spec(cls, method_name: str, method: Callable) -> dict[str, Any]:
        signature = inspect.signature(method)
        parameters = signature.parameters
        type_hints = get_type_hints(method)
        tool_spec = {
            "toolSpec": {
                "name": method_name[1:],
                "description": method.__doc__.strip().split("\n")[0] if method.__doc__ else "",
                "inputSchema": {"json": {"type": "object", "properties": {}, "required": []}},
            }
        }
        for param_name, param in parameters.items():
            if param_name in ("self", "kwargs"):
                continue
            param_type = type_hints.get(param_name, str)
            type_mapping = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}
            param_type_str = type_mapping.get(param_type, "string")
            tool_spec["toolSpec"]["inputSchema"]["json"]["properties"][param_name] = {
                "type": param_type_str,
                "description": f"The {param_name.replace('_', ' ')} for {method_name[1:]}",
            }
            if param.default == inspect.Parameter.empty:
                tool_spec["toolSpec"]["inputSchema"]["json"]["required"].append(param_name)
        return tool_spec

    @classmethod
    def _generate_openai_function_spec(cls, method_name: str, method: Callable) -> dict[str, Any]:
        signature = inspect.signature(method)
        parameters = signature.parameters
        type_hints = get_type_hints(method)
        func_spec = {
            "name": method_name[1:],
            "description": method.__doc__.strip().split("\n")[0] if method.__doc__ else "",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
        for param_name, param in parameters.items():
            if param_name in ("self", "kwargs"):
                continue
            param_type = type_hints.get(param_name, str)
            type_mapping = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}
            param_type_str = type_mapping.get(param_type, "string")
            func_spec["parameters"]["properties"][param_name] = {
                "type": param_type_str,
                "description": f"The {param_name.replace('_', ' ')} for {method_name[1:]}",
            }
            if param.default == inspect.Parameter.empty:
                func_spec["parameters"]["required"].append(param_name)
        return func_spec

    def get_tool_method(self, tool_name: str) -> Callable | None:
        """Resolve a tool method by its external name (no underscore)."""
        return getattr(self, f"_{tool_name}", None)

    @abstractmethod
    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name and return a result dict."""
        ...


class ToolRegistry:
    """Holds multiple tool-class instances and routes calls to them."""

    def __init__(self, tool_classes: list[BaseTool] | None = None) -> None:
        self.tool_classes = tool_classes or []
        self._tool_map: dict[str, BaseTool] = {}
        self._build_tool_map()

    def _build_tool_map(self) -> None:
        self._tool_map = {}
        for tool_class in self.tool_classes:
            methods = inspect.getmembers(tool_class, predicate=inspect.ismethod)
            for method_name, _ in methods:
                if method_name.startswith("_") and not method_name.startswith("__"):
                    tool_name = method_name[1:]
                    if tool_class.enabled_tools is None or tool_name in tool_class.enabled_tools:
                        self._tool_map[tool_name] = tool_class
        logger.info(
            "Tool registry initialised",
            extra={"event": "tools.registry", "count": len(self._tool_map), "tools": list(self._tool_map.keys())},
        )

    def generate_tool_config(self) -> dict[str, Any]:
        """Bedrock toolConfig for every registered tool."""
        if not self.tool_classes:
            return {}
        all_tools: list[dict[str, Any]] = []
        for tool_class in self.tool_classes:
            config = tool_class.__class__.generate_bedrock_config(enabled_tools=tool_class.enabled_tools)
            all_tools.extend(config.get("tools", []))
        return {"tools": all_tools, "toolChoice": {"auto": {}}}

    def generate_openai_functions(self) -> list[dict[str, Any]]:
        """OpenAI functions config for every registered tool."""
        if not self.tool_classes:
            return []
        all_functions: list[dict[str, Any]] = []
        for tool_class in self.tool_classes:
            all_functions.extend(tool_class.__class__.generate_openai_config(enabled_tools=tool_class.enabled_tools))
        return all_functions

    async def execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        tool_class = self._tool_map.get(tool_name)
        if not tool_class:
            logger.error("Tool not found", extra={"event": "tools.not_found", "tool": tool_name})
            return {"success": False, "error": f"Tool '{tool_name}' not found in registry"}
        try:
            return await tool_class.execute(tool_name, tool_input)
        except Exception as e:  # noqa: BLE001
            logger.error("Tool execution error", extra={"event": "tools.error", "tool": tool_name, "error": str(e)}, exc_info=True)
            return {"success": False, "error": str(e)}

    def add_tool_class(self, tool_class: BaseTool) -> None:
        self.tool_classes.append(tool_class)
        self._build_tool_map()

    def get_available_tools(self) -> list[str]:
        return list(self._tool_map.keys())
