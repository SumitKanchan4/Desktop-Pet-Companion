"""
tools.py — LangChain tool definitions for the desktop pet (Buddy).
These tools are bound to the Ollama client and run as part of the agent's think loop.
They use callbacks registered by the main application to interact with UI and skills safely.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from langchain_core.tools import tool

if TYPE_CHECKING:
    from intelligence.slm_client import SLMClient


def get_tools(client: SLMClient) -> list:
    """Returns the list of LangChain tools bound to the client instance."""

    @tool
    def get_current_time() -> str:
        """Returns the current date and time on the user's system. Use this when the user asks for the current time, date, or day."""
        if hasattr(client, "_tools_callbacks") and "get_current_time" in client._tools_callbacks:
            return client._tools_callbacks["get_current_time"]()
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %I:%M %p")

    @tool
    def get_weather_info() -> str:
        """Returns the current weather conditions (temperature, condition, feels like temperature, wind, humidity). Use this when the user asks about the weather outside."""
        if hasattr(client, "_tools_callbacks") and "get_weather" in client._tools_callbacks:
            return client._tools_callbacks["get_weather"]()
        return "Weather information is currently unavailable."

    @tool
    def get_system_resources() -> str:
        """Checks the user's computer system resource usage (CPU and RAM/memory usage percentage). Use this when the user asks how the computer is doing, asks about system load, or requests CPU/RAM status."""
        if hasattr(client, "_tools_callbacks") and "get_system_resources" in client._tools_callbacks:
            return client._tools_callbacks["get_system_resources"]()
        import psutil
        return f"CPU Usage: {psutil.cpu_percent()}%, RAM Usage: {psutil.virtual_memory().percent}%"

    @tool
    def calculate(expression: str) -> str:
        """Evaluates a basic mathematical expression (e.g. '2 + 2', '100 / 5 * 2'). Only supports basic mathematical operations (+, -, *, /, parentheses)."""
        import re
        try:
            # Strictly filter expression to only allow safe mathematical characters
            cleaned = re.sub(r"[^0-9\+\-\*\/\(\)\s\.]", "", expression)
            if not cleaned.strip():
                return "Invalid math expression."
            # Evaluate using safe dictionary
            val = eval(cleaned, {"__builtins__": None}, {})
            return f"Result of {expression} is: {val}"
        except Exception as e:
            return f"Error evaluating expression: {e}"

    @tool
    def pet_action(action: str) -> str:
        """Triggers a physical action or trick for Buddy the desktop pet to perform.
        Supported actions:
        - 'jump': Buddy does a happy hop/jump.
        - 'walk': Buddy walks to a random spot on the screen.
        - 'bark': Buddy plays a barking sound.
        - 'mood_happy': Sets Buddy's mood to energetic/happy.
        - 'mood_sleep': Sets Buddy's mood to sleepy.
        
        Use this when the user tells you to do a trick, walk, jump, bark, or change how you feel.
        """
        if hasattr(client, "_tools_callbacks") and "pet_action" in client._tools_callbacks:
            return client._tools_callbacks["pet_action"](action)
        return f"Action '{action}' triggered."

    return [get_current_time, get_weather_info, get_system_resources, calculate, pet_action]
