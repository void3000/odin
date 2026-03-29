#!/usr/bin/env python3
"""
Script to validate all example IR JSON files.

This demonstrates loading IR from JSON files and validating them
against a sample database schema.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ir.models import QueryIR
from src.ir.validator import IRValidator

# Sample schema matching the examples
SAMPLE_SCHEMA = {
    "users": {
        "id": "int",
        "name": "str",
        "email": "str",
        "status": "str",
        "tier": "str",
        "age": "int",
        "verified": "bool",
    },
    "orders": {
        "id": "int",
        "user_id": "int",
        "total": "float",
        "created_at": "datetime",
    },
    "products": {
        "id": "int",
        "name": "str",
        "price": "float",
        "category": "str",
    },
}


def validate_example(json_path: Path, schema: dict) -> None:
    """Load and validate a single example IR file."""
    print(f"\n{'='*60}")
    print(f"Validating: {json_path.name}")
    print(f"{'='*60}")

    # Load JSON
    with open(json_path) as f:
        ir_data = json.load(f)

    print("\nJSON IR:")
    print(json.dumps(ir_data, indent=2))

    # Parse into Pydantic model
    try:
        query_ir = QueryIR(**ir_data)
        print("\n✓ Pydantic validation passed")
    except Exception as e:
        print(f"\n✗ Pydantic validation failed: {e}")
        return

    # Validate against schema
    validator = IRValidator(schema)
    try:
        validator.validate(query_ir)
        print("✓ Semantic validation passed")
    except Exception as e:
        print(f"✗ Semantic validation failed: {e}")
        return

    print(f"\n✅ {json_path.name} is VALID!")


def main():
    """Validate all example JSON files."""
    examples_dir = Path(__file__).parent
    json_files = sorted(examples_dir.glob("*.json"))

    print("\n" + "="*60)
    print("IR Example Validation")
    print("="*60)
    print(f"\nFound {len(json_files)} example files")

    for json_file in json_files:
        validate_example(json_file, SAMPLE_SCHEMA)

    print("\n" + "="*60)
    print("Validation Complete!")
    print("="*60)


if __name__ == "__main__":
    main()
