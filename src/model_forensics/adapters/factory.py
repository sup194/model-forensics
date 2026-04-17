"""Adapter factory."""

from __future__ import annotations

from model_forensics.schemas import ModelTarget

from .anthropic import AnthropicAdapter
from .base import ModelAdapter
from .openai import GenericOpenAIAdapter, OpenAIAdapter


def create_adapter(target: ModelTarget) -> ModelAdapter:
    """Create an adapter from target configuration."""
    if target.protocol == "anthropic":
        return AnthropicAdapter(target)
    if target.provider == "openai":
        return OpenAIAdapter(target)
    return GenericOpenAIAdapter(target)
