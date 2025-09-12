"""Task registry for managing task definitions and lookups."""

import asyncio
import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskRegistry:
    """Registry for managing task functions and their metadata."""
    
    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
    
    def register_task(
        self,
        name: str,
        function: Callable[..., Awaitable[Any]],
        description: Optional[str] = None,
        is_system_task: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Register a task function.
        
        Args:
            name: Unique task name
            function: Async function to register
            description: Task description
            is_system_task: Whether this is a system-defined task
            metadata: Additional metadata for the task
            
        Raises:
            ValueError: If function is not async or doesn't have proper signature
        """
        # Validate function
        if not asyncio.iscoroutinefunction(function):
            raise ValueError(f"Task function {name} must be async")
        
        # Check function signature - first parameter should be context
        sig = inspect.signature(function)
        params = list(sig.parameters.keys())
        if not params or params[0] != 'context':
            raise ValueError(
                f"Task function {name} must have 'context' as first parameter. "
                f"Got parameters: {params}"
            )
        
        if name in self._tasks:
            logger.warning(f"Task {name} is already registered, overriding")
        
        self._tasks[name] = {
            "function": function,
            "description": description,
            "is_system_task": is_system_task,
            "metadata": metadata or {},
        }
        
        logger.info(f"Registered task: {name} -> {function.__name__}")
    
    def unregister_task(self, name: str) -> None:
        """Unregister a task."""
        if name in self._tasks:
            del self._tasks[name]
            logger.info(f"Unregistered task: {name}")
        else:
            logger.warning(f"Task {name} not found in registry")
    
    def get_task_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get task information by name."""
        info = self._tasks.get(name)
        if info:
            # Return a copy without the actual function for serialization
            return {
                "name": name,
                "description": info["description"],
                "is_system_task": info["is_system_task"],
                "metadata": info["metadata"],
                "function_name": info["function"].__name__,
            }
        return None
    
    def get_function(self, name: str) -> Optional[Callable[..., Awaitable[Any]]]:
        """Get the actual function by name."""
        info = self._tasks.get(name)
        return info["function"] if info else None
    
    def list_tasks(self, system_only: bool = False) -> List[Dict[str, Any]]:
        """List all registered tasks.
        
        Args:
            system_only: If True, only return system tasks
            
        Returns:
            List of task information dictionaries
        """
        tasks = []
        for name, info in self._tasks.items():
            if system_only and not info.get("is_system_task", False):
                continue
            
            task_info = {
                "name": name,
                "description": info["description"],
                "is_system_task": info["is_system_task"],
                "metadata": info["metadata"],
                "function_name": info["function"].__name__,
            }
            tasks.append(task_info)
        
        return tasks
    
    def validate_function(self, function: Callable) -> bool:
        """Validate that a function has the correct signature.
        
        Args:
            function: Function to validate
            
        Returns:
            True if the function is valid, False otherwise
        """
        try:
            if not asyncio.iscoroutinefunction(function):
                return False
            
            sig = inspect.signature(function)
            params = list(sig.parameters.keys())
            return len(params) > 0 and params[0] == 'context'
        except Exception:
            return False
    
    def clear(self) -> None:
        """Clear all registered tasks."""
        self._tasks.clear()
        logger.info("Cleared all registered tasks")
    
    def __contains__(self, name: str) -> bool:
        """Check if a task is registered."""
        return name in self._tasks
    
    def __len__(self) -> int:
        """Get the number of registered tasks."""
        return len(self._tasks)


# Global task registry instance
task_registry = TaskRegistry()


def register_system_task(
    name: str,
    description: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Callable:
    """Decorator to register a system task.
    
    Args:
        name: Unique task name
        description: Task description
        metadata: Additional metadata
        
    Returns:
        The original function (unchanged)
    """
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        task_registry.register_task(
            name=name,
            function=func,
            description=description,
            is_system_task=True,
            metadata=metadata
        )
        return func
    
    return decorator