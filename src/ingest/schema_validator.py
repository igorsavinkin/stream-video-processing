"""Schema validator for inference event metadata."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("schema_validator")

try:
    import jsonschema
    from jsonschema import ValidationError, validate
except ImportError:
    jsonschema = None
    ValidationError = Exception
    validate = None
    logger.warning(
        "jsonschema not installed. Schema validation will be disabled. "
        "Install with: pip install jsonschema"
    )


class SchemaValidationError(Exception):
    """Raised when schema validation fails."""

    pass


class InferenceEventValidator:
    """Validator for inference event metadata against JSON schema."""

    def __init__(self, schema_path: Path | None = None):
        """Initialize validator with schema.

        Args:
            schema_path: Path to JSON schema file. If None, uses default schema.
        """
        self.schema_path = schema_path or self._get_default_schema_path()
        self.schema = self._load_schema()
        self._validate_available()

    def _get_default_schema_path(self) -> Path:
        """Get default schema path relative to project root."""
        # Assuming this file is in src/ingest/, schema is in schemas/ at project root
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent
        return project_root / "schemas" / "inference_event.json"

    def _load_schema(self) -> dict[str, Any]:
        """Load JSON schema from file."""
        if not self.schema_path.exists():
            raise FileNotFoundError(
                f"Schema file not found: {self.schema_path}. "
                "Please ensure schemas/inference_event.json exists."
            )
        try:
            with open(self.schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            logger.debug("Loaded schema from %s", self.schema_path)
            return schema
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in schema file {self.schema_path}: {e}") from e

    def _validate_available(self) -> None:
        """Check if jsonschema library is available."""
        if jsonschema is None:
            logger.warning(
                "jsonschema library not available. Validation will be skipped. "
                "Install with: pip install jsonschema"
            )

    def validate(self, event: dict[str, Any]) -> bool:
        """Validate event against schema.

        Args:
            event: Event dictionary to validate

        Returns:
            True if valid

        Raises:
            SchemaValidationError: If validation fails
        """
        if jsonschema is None:
            logger.debug("Schema validation skipped (jsonschema not available)")
            return True

        try:
            validate(instance=event, schema=self.schema)
            logger.debug("Event validated successfully")
            return True
        except ValidationError as e:
            error_msg = f"Schema validation failed: {e.message}"
            if e.path:
                error_msg += f" at path: {'.'.join(str(p) for p in e.path)}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error during validation: {e}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg) from e

    def validate_or_warn(self, event: dict[str, Any]) -> bool:
        """Validate event, but only log warning on failure instead of raising.

        Args:
            event: Event dictionary to validate

        Returns:
            True if valid, False if invalid
        """
        try:
            return self.validate(event)
        except SchemaValidationError as e:
            logger.warning("Event validation failed (non-fatal): %s", e)
            return False


# Global validator instance (lazy-loaded)
_validator: InferenceEventValidator | None = None


def get_validator() -> InferenceEventValidator:
    """Get or create global validator instance."""
    global _validator
    if _validator is None:
        _validator = InferenceEventValidator()
    return _validator


def validate_event(event: dict[str, Any], strict: bool = False) -> bool:
    """Convenience function to validate an event.

    Args:
        event: Event dictionary to validate
        strict: If True, raises exception on validation failure. If False, only logs warning.

    Returns:
        True if valid, False if invalid (only when strict=False)

    Raises:
        SchemaValidationError: If validation fails and strict=True
    """
    validator = get_validator()
    if strict:
        return validator.validate(event)
    else:
        return validator.validate_or_warn(event)
