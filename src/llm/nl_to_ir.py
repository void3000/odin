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


def _generate_ir_spec() -> str:
    """Generate a compact IR format specification from the Pydantic models.

    This ensures the LLM prompt always matches the actual IR grammar.
    """
    schema = QueryIR.model_json_schema()
    defs = schema.get("$defs", {})

    def _format_enum(values):
        return " | ".join(f'"{v}"' for v in values)

    def _format_props(model_name: str) -> str:
        model_def = defs.get(model_name, {})
        props = model_def.get("properties", {})
        required = set(model_def.get("required", []))
        lines = []
        for name, info in props.items():
            req = "(required)" if name in required else "(optional)"
            desc = info.get("description", "")
            if "enum" in info:
                desc += f" Values: {_format_enum(info['enum'])}"
            elif "anyOf" in info:
                for option in info["anyOf"]:
                    if "enum" in option:
                        desc += f" Values: {_format_enum(option['enum'])}"
            lines.append(f"    - {name} {req}: {desc}")
        return "\n".join(lines)

    # Build spec from root QueryIR properties
    root_props = schema.get("properties", {})
    root_required = set(schema.get("required", []))

    spec_lines = ["The IR is a JSON object. Only the fields listed below are allowed.\n"]

    # QueryIR top-level
    spec_lines.append("QueryIR (root object):")
    for name, info in root_props.items():
        req = "(required)" if name in root_required else "(optional)"
        desc = info.get("description", "")
        spec_lines.append(f"  - {name} {req}: {desc}")

    # Sub-models
    for model_name in ["TableSource", "FieldExpr", "JoinExpr", "ConditionExpr", "LogicalExpr", "OrderExpr"]:
        if model_name in defs:
            model_desc = defs[model_name].get("description", "").split("\n")[0]
            spec_lines.append(f"\n{model_name}: {model_desc}")
            spec_lines.append(_format_props(model_name))

    return "\n".join(spec_lines)


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
        ir_spec = _generate_ir_spec()

        return f"""You are a SQL query translator. Convert natural language queries into a structured JSON format called IR (Intermediate Representation).

DATABASE SCHEMA:
{schema_text}

IR FORMAT SPECIFICATION (auto-generated from schema — this is the ONLY valid format):

{ir_spec}

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

STRICT RULES - VIOLATIONS WILL CAUSE ERRORS:
1. Always include "operation": "SELECT"
2. Use table qualifiers (table field) when doing JOINs
3. For JOIN conditions, use nested dict format: {{"field": "...", "table": "..."}} for both sides
4. LIKE patterns need % wildcards: "%search%"
5. Milliseconds are used for duration (60000 = 1 minute)
6. Only output valid JSON - no explanations, no markdown, no text before or after the JSON
7. Match table and column names EXACTLY as shown in schema (case-sensitive)
8. The ONLY allowed values for "function" are: "COUNT", "SUM", "AVG", "MIN", "MAX"
   - DISTINCT is NOT supported. Do not use it anywhere.
   - No other function names are valid. If a query needs an unsupported function, approximate using only the allowed ones.
9. The ONLY allowed fields in each object are those defined above. Do not invent new fields.
10. If you cannot represent a query using the IR format above, use the closest possible approximation.

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
