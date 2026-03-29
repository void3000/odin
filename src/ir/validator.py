"""
IR Validator

Provides semantic validation for IR structures beyond Pydantic's schema validation.
Validates that tables and fields exist in the database schema, operators match field types,
and logical expressions are well-formed.
"""

from typing import Set, Dict, Any, List
from pydantic import ValidationError

from .models import (
    QueryIR,
    FieldExpr,
    JoinExpr,
    ConditionExpr,
    LogicalExpr,
    FilterExpr,
    OrderExpr,
)


class ValidationError(Exception):
    """Base validation error."""
    pass


class TableNotFoundError(ValidationError):
    """Table does not exist in schema."""
    pass


class FieldNotFoundError(ValidationError):
    """Field does not exist in table."""
    pass


class TypeMismatchError(ValidationError):
    """Operator type does not match field type."""
    pass


class IRValidator:
    """
    Validates IR structures against a database schema.

    Performs semantic validation including:
    - Table existence
    - Field existence in their tables
    - Type compatibility between operators and field types
    - Logical expression correctness
    """

    def __init__(self, schema: Dict[str, Dict[str, str]]):
        """
        Initialize the validator with a database schema.

        Args:
            schema: Dictionary mapping table names to field definitions.
                   Format: {"table_name": {"field_name": "field_type", ...}, ...}
                   Example: {
                       "users": {"id": "int", "name": "str", "age": "int"},
                       "orders": {"id": "int", "user_id": "int", "total": "float"}
                   }
        """
        self.schema = schema

    def validate(self, query_ir: QueryIR) -> None:
        """
        Validate a complete QueryIR against the schema.

        Args:
            query_ir: The QueryIR to validate

        Raises:
            ValidationError: If any validation check fails
        """
        # Validate source table
        self._validate_table(query_ir.source.table)

        # Collect all tables involved in the query
        tables = {query_ir.source.table}

        # Validate joins
        if query_ir.joins:
            for join in query_ir.joins:
                self._validate_join(join, tables)
                tables.add(join.table)

        # Validate fields
        for field in query_ir.fields:
            self._validate_field_expr(field, tables)

        # Validate filters
        if query_ir.filters:
            self._validate_filter_expr(query_ir.filters, tables)

        # Validate order_by
        if query_ir.order_by:
            for order_expr in query_ir.order_by:
                self._validate_order_expr(order_expr, tables)

    def _validate_table(self, table: str) -> None:
        """Validate that a table exists in the schema."""
        if table not in self.schema:
            raise TableNotFoundError(
                f"Table '{table}' not found in schema. "
                f"Available tables: {', '.join(self.schema.keys())}"
            )

    def _validate_field_in_table(self, field: str, table: str) -> str:
        """
        Validate that a field exists in a table and return its type.

        Args:
            field: Field name
            table: Table name

        Returns:
            Field type as string

        Raises:
            FieldNotFoundError: If field doesn't exist in table
        """
        if field == "*":
            return "any"

        if table not in self.schema:
            raise TableNotFoundError(f"Table '{table}' not found")

        if field not in self.schema[table]:
            raise FieldNotFoundError(
                f"Field '{field}' not found in table '{table}'. "
                f"Available fields: {', '.join(self.schema[table].keys())}"
            )

        return self.schema[table][field]

    def _validate_field_expr(self, field_expr: FieldExpr, available_tables: Set[str]) -> None:
        """Validate a FieldExpr."""
        # If table is specified, validate it
        if field_expr.table:
            if field_expr.table not in available_tables:
                raise ValidationError(
                    f"Table '{field_expr.table}' referenced in field expression "
                    f"but not available in query. Available: {', '.join(available_tables)}"
                )
            self._validate_field_in_table(field_expr.field, field_expr.table)
        else:
            # If no table specified, field must exist in at least one available table
            if field_expr.field != "*":
                found = False
                for table in available_tables:
                    try:
                        self._validate_field_in_table(field_expr.field, table)
                        found = True
                        break
                    except FieldNotFoundError:
                        continue

                if not found:
                    raise FieldNotFoundError(
                        f"Field '{field_expr.field}' not found in any available table: "
                        f"{', '.join(available_tables)}"
                    )

    def _validate_join(self, join_expr: JoinExpr, existing_tables: Set[str]) -> None:
        """Validate a JoinExpr."""
        # Validate the joined table exists
        self._validate_table(join_expr.table)

        # Validate the join condition
        # The condition should reference fields from existing tables and the new table
        all_tables = existing_tables | {join_expr.table}
        self._validate_condition_expr(join_expr.on, all_tables)

    def _validate_condition_expr(
        self, condition: ConditionExpr, available_tables: Set[str]
    ) -> None:
        """Validate a ConditionExpr."""
        # Determine which table the field belongs to
        if condition.table:
            if condition.table not in available_tables:
                raise ValidationError(
                    f"Table '{condition.table}' in condition not available. "
                    f"Available: {', '.join(available_tables)}"
                )
            field_type = self._validate_field_in_table(condition.field, condition.table)
        else:
            # Try to find the field in available tables
            field_type = None
            for table in available_tables:
                try:
                    field_type = self._validate_field_in_table(condition.field, table)
                    break
                except FieldNotFoundError:
                    continue

            if field_type is None:
                raise FieldNotFoundError(
                    f"Field '{condition.field}' not found in any available table"
                )

        # Validate operator compatibility with field type
        self._validate_operator_type(condition.op, field_type, condition.value)

    def _validate_filter_expr(self, filter_expr: FilterExpr, available_tables: Set[str]) -> None:
        """Validate a FilterExpr (recursive for LogicalExpr)."""
        if isinstance(filter_expr, ConditionExpr):
            self._validate_condition_expr(filter_expr, available_tables)
        elif isinstance(filter_expr, LogicalExpr):
            for sub_condition in filter_expr.conditions:
                self._validate_filter_expr(sub_condition, available_tables)
        else:
            raise ValidationError(f"Unknown filter expression type: {type(filter_expr)}")

    def _validate_order_expr(self, order_expr: OrderExpr, available_tables: Set[str]) -> None:
        """Validate an OrderExpr."""
        if order_expr.table:
            if order_expr.table not in available_tables:
                raise ValidationError(
                    f"Table '{order_expr.table}' in ORDER BY not available"
                )
            self._validate_field_in_table(order_expr.field, order_expr.table)
        else:
            # Field must exist in at least one table
            found = False
            for table in available_tables:
                try:
                    self._validate_field_in_table(order_expr.field, table)
                    found = True
                    break
                except FieldNotFoundError:
                    continue

            if not found:
                raise FieldNotFoundError(
                    f"Field '{order_expr.field}' in ORDER BY not found in any available table"
                )

    def _validate_operator_type(self, op: str, field_type: str, value: Any) -> None:
        """
        Validate that an operator is compatible with a field type and value.

        Args:
            op: The operator (=, !=, >, >=, <, <=, LIKE, IN)
            field_type: The type of the field (int, float, str, bool, etc.)
            value: The value being compared

        Raises:
            TypeMismatchError: If operator is incompatible with field type
        """
        # LIKE operator only works with strings
        if op == "LIKE":
            if field_type not in ("str", "string", "text", "varchar"):
                raise TypeMismatchError(
                    f"LIKE operator requires string field, got '{field_type}'"
                )
            if not isinstance(value, str):
                raise TypeMismatchError(
                    f"LIKE operator requires string value, got {type(value).__name__}"
                )

        # Comparison operators (>, >=, <, <=) require numeric types
        elif op in (">", ">=", "<", "<="):
            if field_type not in ("int", "integer", "float", "double", "decimal", "numeric"):
                raise TypeMismatchError(
                    f"Comparison operator '{op}' requires numeric field, got '{field_type}'"
                )
            # Value could be a dict (field reference) or a number
            if not isinstance(value, (int, float, dict)):
                raise TypeMismatchError(
                    f"Comparison operator '{op}' requires numeric value, "
                    f"got {type(value).__name__}"
                )

        # IN operator
        elif op == "IN":
            if not isinstance(value, list):
                raise TypeMismatchError(
                    f"IN operator requires list value, got {type(value).__name__}"
                )

            # Check that list values match field type
            if field_type in ("int", "integer"):
                for v in value:
                    if not isinstance(v, int):
                        raise TypeMismatchError(
                            f"IN operator with integer field requires integer values, "
                            f"got {type(v).__name__}"
                        )
            elif field_type in ("float", "double", "decimal", "numeric"):
                for v in value:
                    if not isinstance(v, (int, float)):
                        raise TypeMismatchError(
                            f"IN operator with numeric field requires numeric values, "
                            f"got {type(v).__name__}"
                        )

        # Equality operators (=, !=) are generally permissive but we can add checks
        # For field references (dict values), skip value type checking


def validate_query_ir(query_ir: QueryIR, schema: Dict[str, Dict[str, str]]) -> None:
    """
    Convenience function to validate a QueryIR against a schema.

    Args:
        query_ir: The QueryIR to validate
        schema: Database schema definition

    Raises:
        ValidationError: If validation fails
    """
    validator = IRValidator(schema)
    validator.validate(query_ir)
