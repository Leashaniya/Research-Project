from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BaseAgent(ABC):
    """
    Abstract Base Class for all Agents.
    Enforces a common interface for 'run' and configuration.
    """

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}

    @abstractmethod
    async def run(self, input_data: Any) -> Any:
        """
        Main entry point for the agent's logic.
        :param input_data: The input payload for the agent (differs by agent type).
        :return: The result of the agent's work.
        """
        pass

    def log(self, message: str):
        """Standardized internal logging."""
        print(f"[{self.name.upper()}]: {message}")
