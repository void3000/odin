"""
IR Parser Module.

Parses natural language queries into IR (Intermediate Representation)
using an LLM client.
"""

import json
import logging
from typing import Any, Dict, Tuple

from pydantic import ValidationError

from src.ir.models import QueryIR
from src.logging_config import get_component_logger

logger = get_component_logger("ir.parser")


class IRParser:
    """
    Parses natural language queries into IR using an LLM.
    
    This module handles the first stage of the query pipeline:
    Converting user's natural language question into a structured IR format.
    """
    
    def __init__(self, llm_client: Any, system_prompt: str):
        """
        Initialize the parser with LLM client and system prompt.
        
        Args:
            llm_client: LLMClient instance for generating IR
            system_prompt: System message containing schema context
        """
        self.llm_client = llm_client
        self.system_prompt = system_prompt
    
    def parse(self, natural_language: str, conversation_history=None) -> Dict[str, Any]:
        """
        Parse a natural language query into IR.

        Args:
            natural_language: User's question in natural language
            conversation_history: Optional list of ConversationTurn for context

        Returns:
            Dict with 'success' boolean and either 'data' (QueryIR) or 'error'
        """
        try:
            # Call LLM to generate IR JSON
            user_message = self._build_user_message(natural_language, conversation_history)
            success, response = self.llm_client.generate(
                system_prompt=self.system_prompt,
                user_message=user_message,
            )
            
            if not success:
                return {
                    "success": False,
                    "error": f"LLM generation failed: {response}"
                }
            
            # Extract JSON from response (handle markdown code blocks)
            ir_json = self._extract_json(response)

            # If the LLM returned prose instead of JSON, surface its message
            stripped = ir_json.strip()
            if not stripped.startswith("{") and not stripped.startswith("["):
                logger.info(f"LLM declined to generate IR: {stripped[:100]}...")
                return {
                    "success": False,
                    "error": stripped,
                }

            # Check if the LLM returned a JSON error object instead of IR
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict) and "error" in parsed:
                    error_info = parsed["error"]
                    msg = error_info.get("message", str(error_info)) if isinstance(error_info, dict) else str(error_info)
                    logger.info(f"LLM returned error object: {msg}")
                    return {
                        "success": False,
                        "error": msg,
                    }
            except json.JSONDecodeError:
                pass  # Will be caught below

            # Parse and validate as QueryIR
            try:
                query_ir = QueryIR.model_validate_json(ir_json)
                logger.info(f"Successfully parsed IR for: {natural_language[:50]}...")
                return {
                    "success": True,
                    "data": query_ir
                }
            except ValidationError as e:
                error_msg = f"LLM output is not valid IR format:\n{e}\n\nRaw output:\n{ir_json}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"LLM output is not valid JSON: {e}\n\nRaw output:\n{response}"
                }
                
        except Exception as e:
            error_msg = f"Unexpected error during parsing: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg
            }
    
    def _build_user_message(self, natural_language: str, conversation_history=None) -> str:
        """Build the user message, optionally including conversation history."""
        if not conversation_history:
            return natural_language

        lines = ["Previous conversation:"]
        for turn in conversation_history:
            lines.append(f"User: {turn.question}")
            lines.append(f"Assistant: {turn.summary}")
            lines.append("")
        lines.append(f"Current question: {natural_language}")
        return "\n".join(lines)

    def _extract_json(self, content: str) -> str:
        """
        Extract JSON from LLM response (handles markdown code blocks).
        
        Args:
            content: Raw LLM response
            
        Returns:
            Cleaned JSON string
        """
        content = content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]  # Remove ```json
        elif content.startswith("```"):
            content = content[3:]  # Remove ```
        
        if content.endswith("```"):
            content = content[:-3]  # Remove trailing ```
        
        return content.strip()
