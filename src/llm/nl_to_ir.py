"""
Natural Language to IR Converter using LM Studio

This module uses LM Studio's OpenAI-compatible API to convert natural language queries
into structured IR (Intermediate Representation) that can be executed by
the query pipeline.
"""
import json
from typing import Optional
from openai import OpenAI
from pydantic import ValidationError

from src.ir.models import QueryIR
from src.schema.schema import DatabaseSchema


class NaturalLanguageToIR:
    """Converts natural language queries to IR using LLM."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model_name: str = "qwen3.5-27b-claude-4.6-opus-reasoning-distilled",
        temperature: float = 0.1,
        api_key: Optional[str] = None
    ):
        """
        Initialize the NL to IR converter.

        Args:
            base_url: LM Studio API base URL (default: http://localhost:1234/v1)
            model_name: Model name (default: "local-model")
            temperature: Model temperature (0.0 for deterministic)
            api_key: API key (optional, LM Studio doesn't require one)
        """
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )
        self.model_name = model_name
        self.temperature = temperature

    def convert(
        self,
        natural_query: str,
        schema: DatabaseSchema
    ) -> QueryIR:
        """
        Convert a natural language query to IR.

        Args:
            natural_query: Natural language query (e.g., "Show me all artists")
            schema: Database schema for context

        Returns:
            QueryIR: Structured query representation

        Raises:
            ValueError: If LLM output cannot be parsed as valid IR
        """
        system_prompt = self._build_system_prompt(schema)
        user_prompt = f"Natural language query: {natural_query}"

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=self.temperature
        )

        ir_json = self._extract_json(response.choices[0].message.content)

        try:
            query_ir = QueryIR.model_validate_json(ir_json)
            return query_ir
        except ValidationError as e:
            raise ValueError(f"Failed to parse LLM output as valid IR: {e}")

    def _build_system_prompt(self, schema: DatabaseSchema) -> str:
        """Build the system prompt with schema context and IR format."""
        schema_text = self._format_schema(schema)

        return f"""You are a SQL query translator. Convert natural language queries into a structured JSON format called IR (Intermediate Representation).

DATABASE SCHEMA:
{schema_text}

IR FORMAT SPECIFICATION:

The IR is a JSON object with these fields:

1. "operation": Always "SELECT" (only SELECT queries supported)

2. "source": The main table to query
   {{"table": "table_name"}}

3. "fields": List of columns to retrieve
   [{{"field": "column_name", "table": "table_name", "alias": "optional_alias", "function": "optional_aggregate"}}]
   - Use "table" when joining multiple tables
   - Use "alias" to rename output columns
   - Use "function" for aggregates: "COUNT", "SUM", "AVG", "MIN", "MAX"
   - COUNT can use "*" as the field (e.g., {{"field": "*", "function": "COUNT"}})
   - SUM, AVG, MIN, MAX require a specific column name

4. "joins": Optional list of JOIN operations
   [{{
     "type": "INNER" | "LEFT" | "RIGHT",
     "table": "table_to_join",
     "on": {{"field": "col1", "table": "table1", "op": "=", "value": {{"field": "col2", "table": "table2"}}}}
   }}]

5. "filters": Optional WHERE conditions
   - Simple condition: {{"field": "column", "table": "table", "op": "=", "value": 123}}
   - Operators: "=", "!=", ">", ">=", "<", "<=", "LIKE", "IN"
   - Logical AND/OR: {{"logic": "AND", "conditions": [condition1, condition2]}}

6. "order_by": Optional sorting
   [{{"field": "column", "table": "table", "direction": "ASC" | "DESC"}}]

7. "limit": Optional row limit (integer)

EXAMPLES:

Query: "Show me all artists"
{{
  "operation": "SELECT",
  "source": {{"table": "Artist"}},
  "fields": [
    {{"field": "ArtistId", "alias": "id"}},
    {{"field": "Name", "alias": "name"}}
  ]
}}

Query: "Find AC/DC's albums"
{{
  "operation": "SELECT",
  "source": {{"table": "Artist"}},
  "fields": [
    {{"field": "Name", "table": "Artist", "alias": "artist"}},
    {{"field": "Title", "table": "Album", "alias": "album"}}
  ],
  "joins": [{{
    "type": "INNER",
    "table": "Album",
    "on": {{"field": "ArtistId", "table": "Artist", "op": "=", "value": {{"field": "ArtistId", "table": "Album"}}}}
  }}],
  "filters": {{"field": "Name", "table": "Artist", "op": "=", "value": "AC/DC"}}
}}

Query: "Show rock tracks longer than 5 minutes, sorted by duration"
{{
  "operation": "SELECT",
  "source": {{"table": "Track"}},
  "fields": [
    {{"field": "Name", "table": "Track", "alias": "track"}},
    {{"field": "Milliseconds", "table": "Track", "alias": "duration"}},
    {{"field": "Name", "table": "Genre", "alias": "genre"}}
  ],
  "joins": [{{
    "type": "INNER",
    "table": "Genre",
    "on": {{"field": "GenreId", "table": "Track", "op": "=", "value": {{"field": "GenreId", "table": "Genre"}}}}
  }}],
  "filters": {{
    "logic": "AND",
    "conditions": [
      {{"field": "Name", "table": "Genre", "op": "=", "value": "Rock"}},
      {{"field": "Milliseconds", "table": "Track", "op": ">", "value": 300000}}
    ]
  }},
  "order_by": [{{"field": "Milliseconds", "table": "Track", "direction": "DESC"}}]
}}

Query: "How many artists are there?"
{{
  "operation": "SELECT",
  "source": {{"table": "Artist"}},
  "fields": [
    {{"field": "*", "function": "COUNT", "alias": "artist_count"}}
  ]
}}

IMPORTANT RULES:
1. Always include "operation": "SELECT"
2. Use table qualifiers (table field) when doing JOINs
3. For JOIN conditions, use nested dict format: {{"field": "...", "table": "..."}} for both sides
4. LIKE patterns need % wildcards: "%search%"
5. Milliseconds are used for duration (60000 = 1 minute)
6. Only output valid JSON - no explanations or markdown
7. Match table and column names exactly as shown in schema
8. The only supported aggregate functions are: COUNT, SUM, AVG, MIN, MAX. Do not use DISTINCT or any other function

Now convert the user's query to IR JSON:"""

    def _format_schema(self, schema: DatabaseSchema) -> str:
        """Format database schema for the prompt."""
        lines = []
        for table in schema.tables:
            columns = []
            for col in table.columns:
                col_def = f"{col.name} ({col.type})"
                if col.primary_key:
                    col_def += " PRIMARY KEY"
                if col.foreign_key:
                    col_def += f" -> {col.foreign_key}"
                columns.append(col_def)

            lines.append(f"\n{table.name}:")
            for col in columns:
                lines.append(f"  - {col}")

        return "\n".join(lines)

    def _extract_json(self, content: str) -> str:
        """Extract JSON from LLM response (handles markdown code blocks)."""
        content = content.strip()

        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]  # Remove ```json
        elif content.startswith("```"):
            content = content[3:]  # Remove ```

        if content.endswith("```"):
            content = content[:-3]  # Remove trailing ```

        content = content.strip()

        # Validate it's valid JSON
        try:
            json.loads(content)
            return content
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM output is not valid JSON: {e}\nContent: {content}")
