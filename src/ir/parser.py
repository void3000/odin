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
    
    def parse(self, natural_language: str) -> Dict[str, Any]:
        """
        Parse a natural language query into IR.
        
        Args:
            natural_language: User's question in natural language
            
        Returns:
            Dict with 'success' boolean and either 'data' (QueryIR) or 'error'
        """
        try:
            # Call LLM to generate IR JSON
            success, response = self.llm_client.generate(
                system_prompt=self.system_prompt,
                user_message=natural_language
            )
            
            if not success:
                return {
                    "success": False,
                    "error": f"LLM generation failed: {response}"
                }
            
            # Extract JSON from response (handle markdown code blocks)
            ir_json = self._extract_json(response)
            
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
