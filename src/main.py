"""
Main entry point for Text2SQL system.

Provides the main interface for processing natural language queries
and returning database results.
"""

import os
import sys
from typing import Any, Dict, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm_client import LLMClient
from src.schema.extractor import SQLiteSchemaExtractor
from src.orchestrator import QueryOrchestrator
from src.logging_config import setup_logging

# Setup logging first
setup_logging()
import logging

logger = logging.getLogger("main")


class Text2SQL:
    """
    Main interface for the Text2SQL system.
    
    Provides a simple API to convert natural language questions
    into database queries and return results.
    """
    
    def __init__(
        self,
        db_path: str,
        design_document_path: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1
    ):
        """
        Initialize Text2SQL system.
        
        Args:
            db_path: Path to SQLite database file
            design_document_path: Optional path to design document (auto-detected if not provided)
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
            model: LLM model to use for parsing
            temperature: Temperature for LLM generation (lower = more deterministic)
        """
        self.db_path = db_path
        
        # Auto-detect design document if not specified
        if design_document_path is None:
            design_document_path = os.path.splitext(db_path)[0] + ".md"
        
        self.design_document_path = design_document_path
        
        # Initialize LLM client
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY environment variable "
                "or provide api_key parameter"
            )
        
        self.llm_client = LLMClient(api_key, model=model, temperature=temperature)
        logger.info(f"Text2SQL initialized for database: {db_path}")
        logger.debug(f"Using model: {model}, temperature: {temperature}")
    
    def query(self, question: str) -> Dict[str, Any]:
        """
        Process a natural language question and return results.
        
        Args:
            question: Natural language question about the database
            
        Returns:
            Dict with success status, data, error message, and metadata
        """
        logger.info(f"Processing query: {question}")
        
        try:
            # Extract schema from design document
            extractor = SchemaExtractor(self.design_document_path)
            schema = extractor.extract()
            
            if not schema:
                return {
                    "success": False,
                    "error": f"Failed to extract schema from {self.design_document_path}",
                    "data": None
                }
            
            logger.debug(f"Schema extracted: {len(schema)} tables")
            
            # Build system prompt with schema context
            system_prompt = self._build_system_prompt(schema)
            
            # Initialize orchestrator
            orchestrator = QueryOrchestrator(
                db_path=self.db_path,
                llm_client=self.llm_client,
                system_prompt=system_prompt,
                schema=schema
            )
            
            # Process query through pipeline
            result = orchestrator.process_query(question)
            
            return result
            
        except FileNotFoundError as e:
            error_msg = f"File not found: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "data": None
            }
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg,
                "data": None
            }
    
    def _build_system_prompt(self, schema: Dict[str, Any]) -> str:
        """
        Build system prompt with database schema context.
        
        Args:
            schema: Database schema from design document
            
        Returns:
            System prompt string for the LLM parser
        """
        # Format schema as markdown
        schema_text = "\n\n## Database Schema\n\n"
        for table_name, table_info in schema.items():
            columns = table_info.get("columns", {})
            constraints = table_info.get("constraints", [])
            
            schema_text += f"### Table: {table_name}\n\n"
            schema_text += "| Column | Type | Constraints |\n"
            schema_text += "|--------|------|-------------|\n"
            for col_name, col_info in columns.items():
                col_type = col_info.get("type", "unknown")
                constraints_str = ", ".join(constraints) if constraints else "-"
                schema_text += f"| {col_name} | {col_type} | {constraints_str} |\n"
            
            # Add primary key info
            pk = table_info.get("primary_key")
            if pk:
                schema_text += f"\n**Primary Key**: {pk}\n"
            
            # Add foreign keys
            fk_list = [f"{fk['column']} -> {fk['ref_table']}.{fk['ref_column']}" 
                       for fk in constraints if fk.get('type') == 'FOREIGN KEY']
            if fk_list:
                schema_text += f"\n**Foreign Keys**: {'; '.join(fk_list)}\n"
            
            schema_text += "\n---\n\n"
        
        # Build complete system prompt
        system_prompt = f"""You are a Text2SQL parser that converts natural language questions into structured query representations.

{schema_text}
## Instructions:
1. Analyze the user's question and identify which tables and columns are relevant
2. Map natural language conditions to SQL operators (=, <>, >, <, >=, <=, LIKE, IN)
3. Generate a valid JSON object following the QueryIR schema
4. Use table aliases when referencing columns from joined tables
5. Always include at least one field in the SELECT clause
6. For JOINs, use appropriate join types (INNER for required matches, LEFT for optional)
7. Support nested AND/OR conditions for complex filters
8. Return ONLY a JSON object - no explanations or markdown formatting

## Output Format:
Return a valid JSON object matching the QueryIR schema.
"""
        
        return system_prompt
    
    def get_schema_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the database schema.
        
        Returns:
            Dict with table names and column counts
        """
        extractor = SchemaExtractor(self.design_document_path)
        schema = extractor.extract()
        
        if not schema:
            return {"error": "Failed to extract schema"}
        
        summary = {}
        for table_name, table_info in schema.items():
            columns = table_info.get("columns", {})
            summary[table_name] = {
                "column_count": len(columns),
                "columns": list(columns.keys())
            }
        return summary


def main():
    """
    Main entry point for command-line usage.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Text2SQL - Natural Language to SQL")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument("--doc", help="Path to design document (auto-detected if not provided)")
    parser.add_argument("--key", help="OpenAI API key (uses OPENAI_API_KEY env var if not provided)")
    parser.add_argument("--model", default="gpt-4o-mini", help="LLM model to use")
    parser.add_argument("--temperature", type=float, default=0.1, help="Temperature for generation")
    parser.add_argument("--query", required=True, help="Natural language query")
    
    args = parser.parse_args()
    
    # Initialize Text2SQL
    try:
        text2sql = Text2SQL(
            db_path=args.db,
            design_document_path=args.doc,
            api_key=args.key,
            model=args.model,
            temperature=args.temperature
        )
        
        # Process query
        result = text2sql.query(args.query)
        
        # Print result
        if result["success"]:
            print(result["summary"])
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
