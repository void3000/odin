#!/usr/bin/env python3
"""
Demo script for QueryBuilder usage.

Demonstrates how to use the PostgreSQLBuilder to translate
IR examples into SQL queries.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ir.models import QueryIR
from src.query.factory import QueryBuilderFactory
from src.query.postgresql import PostgreSQLBuilder


def demo_simple_query():
    """Demo: Simple SELECT query."""
    print("\n" + "="*60)
    print("Example 1: Simple Query")
    print("="*60)

    # Load IR from examples
    with open('examples/simple_query.json') as f:
        ir_data = json.load(f)

    # Parse IR
    query_ir = QueryIR(**ir_data)
    print(f"\nNatural Language: Get all active users")
    print(f"\nIR: {json.dumps(ir_data, indent=2)}")

    # Build SQL using factory
    builder = QueryBuilderFactory.create("postgresql")
    result = builder.build(query_ir)

    print(f"\n{result}")


def demo_join_query():
    """Demo: Query with JOIN and filters."""
    print("\n" + "="*60)
    print("Example 2: JOIN with Filters")
    print("="*60)

    with open('examples/join_with_filters.json') as f:
        ir_data = json.load(f)

    query_ir = QueryIR(**ir_data)
    print(f"\nNatural Language: Premium users with orders over $100")

    builder = PostgreSQLBuilder()
    result = builder.build(query_ir)

    print(f"\n{result}")
    print(f"\nParameters: {result.params}")


def demo_nested_conditions():
    """Demo: Query with nested logical conditions."""
    print("\n" + "="*60)
    print("Example 3: Nested Conditions")
    print("="*60)

    with open('examples/nested_conditions.json') as f:
        ir_data = json.load(f)

    query_ir = QueryIR(**ir_data)
    print(f"\nNatural Language: VIP users OR (active AND age > 10)")

    builder = PostgreSQLBuilder()
    result = builder.build(query_ir)

    print(f"\n{result}")


def demo_capabilities():
    """Demo: Checking database capabilities."""
    print("\n" + "="*60)
    print("Database Capabilities")
    print("="*60)

    builder = PostgreSQLBuilder()
    capabilities = builder.get_capabilities()

    print(f"\nPostgreSQL Capabilities:")
    print(f"  Supports JOINs: {capabilities.supports_joins}")
    print(f"  Supports Complex Filters: {capabilities.supports_complex_filters}")
    print(f"  Supports Aggregates: {capabilities.supports_aggregates}")
    print(f"  Supported Operators: {', '.join(sorted(capabilities.supported_operators))}")


def demo_factory():
    """Demo: Using the factory pattern."""
    print("\n" + "="*60)
    print("QueryBuilder Factory")
    print("="*60)

    print(f"\nSupported databases: {QueryBuilderFactory.list_supported()}")

    # Create builder dynamically
    db_type = "postgresql"
    builder = QueryBuilderFactory.create(db_type)
    print(f"\nCreated builder for: {db_type}")
    print(f"Builder class: {builder.__class__.__name__}")


def demo_to_dict():
    """Demo: Converting result to dictionary for logging/inspection."""
    print("\n" + "="*60)
    print("Query Result Introspection")
    print("="*60)

    with open('examples/simple_query.json') as f:
        ir_data = json.load(f)

    query_ir = QueryIR(**ir_data)
    builder = PostgreSQLBuilder()
    result = builder.build(query_ir)

    # Convert to dict for logging
    result_dict = result.to_dict()
    print(f"\nResult as dictionary:")
    print(json.dumps(result_dict, indent=2))


def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("PostgreSQL Query Builder Demo")
    print("="*60)

    demo_simple_query()
    demo_join_query()
    demo_nested_conditions()
    demo_capabilities()
    demo_factory()
    demo_to_dict()

    print("\n" + "="*60)
    print("Demo Complete!")
    print("="*60)
    print("\nTo use in your code:")
    print("  from src.query.factory import QueryBuilderFactory")
    print("  builder = QueryBuilderFactory.create('postgresql')")
    print("  result = builder.build(query_ir)")
    print("  print(result.sql, result.params)")
    print()


if __name__ == "__main__":
    main()
