"""
LLM Client Module.

Provides a unified interface for communicating with OpenAI-compatible APIs,
supporting both cloud (OpenAI) and local (LM Studio, Ollama) deployments.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Client for OpenAI-compatible APIs.
    
    Supports both cloud and local model deployments with automatic detection.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1
    ):
        """
        Initialize LLM client.
        
        Args:
            api_key: API key (required for cloud, optional for local)
            base_url: Base URL for local deployments (e.g., http://localhost:1234/v1)
            model: Model name to use
            temperature: Temperature for generation (0.0 = deterministic)
        """
        self.model = model
        self.temperature = temperature
        
        # Configure client based on deployment type
        if base_url:
            # Local deployment (LM Studio, Ollama, etc.)
            self.client = OpenAI(base_url=base_url, api_key=api_key or "local")
            logger.info(f"LLMClient initialized for local model: {model} at {base_url}")
        else:
            # Cloud deployment (OpenAI)
            if not api_key:
                import os
                api_key = os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError(
                        "API key required for cloud deployment. Set OPENAI_API_KEY env var "
                        "or provide api_key parameter"
                    )
            self.client = OpenAI(api_key=api_key)
            logger.info(f"LLMClient initialized for cloud model: {model}")
    
    def generate(self, system_prompt: str, user_message: str) -> Tuple[bool, Any]:
        """
        Generate a response from the LLM.
        
        Args:
            system_prompt: System message providing context
            user_message: User's question or request
            
        Returns:
            Tuple of (success, result_or_error)
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=self.temperature
            )
            
            content = response.choices[0].message.content
            
            # Log token usage if available
            usage = response.usage
            logger.debug(f"Tokens - Input: {usage.prompt_tokens}, "
                        f"Output: {usage.completion_tokens}")
            
            return True, content
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"LLM generation failed: {error_msg}")
            return False, error_msg
