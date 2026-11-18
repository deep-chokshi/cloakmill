"""Format-specific parsing and artifact-writing adapters."""

from cloakmill.formats.csv_format import extract_csv_parts
from cloakmill.formats.extract import FormatExtractResult, extract_parts_for_media_type
from cloakmill.formats.json_format import (
    EMPTY_KEY_SEGMENT,
    LITERAL_KEY_PREFIX,
    ROOT_SEGMENT,
    decode_field_key,
    encode_field_key,
    extract_json_parts,
    extract_jsonl_parts,
)
from cloakmill.formats.text_format import extract_text_parts
from cloakmill.formats.write import (
    SUPPORTED_WRITE_MEDIA_TYPES,
    WriteResult,
    apply_patches,
    write_artifact,
)

__all__ = [
    "EMPTY_KEY_SEGMENT",
    "LITERAL_KEY_PREFIX",
    "ROOT_SEGMENT",
    "SUPPORTED_WRITE_MEDIA_TYPES",
    "FormatExtractResult",
    "WriteResult",
    "apply_patches",
    "decode_field_key",
    "encode_field_key",
    "extract_csv_parts",
    "extract_json_parts",
    "extract_jsonl_parts",
    "extract_parts_for_media_type",
    "extract_text_parts",
    "write_artifact",
]
