"""Prompt template base. Prompts are plain classes that render a string;
agents pass the rendered string to the model as the system prompt."""
from typing import Any


class BasePrompt:
    template: str = ""

    def render(self, **context: Any) -> str:
        try:
            return self.template.format(**context)
        except (KeyError, IndexError, ValueError):
            return self.template
