"""Pure generated-output parsing; no provider dispatch or persistence."""
import json
import posixpath
from typing import cast

from .metadata import validate_metadata


def _reject_number(_value):
    raise ValueError("Numbers are not metadata")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate metadata key")
        result[key] = value
    return result


def _parse(raw, requested_fields, content_mode, safe_basename):
    if type(raw) is not str or len(raw) > 32768 or len(raw.encode("utf-8")) > 32768:
        raise ValueError("Invalid generated metadata")
    result = json.loads(raw, object_pairs_hook=_unique_object,
                        parse_constant=_reject_number, parse_int=_reject_number,
                        parse_float=_reject_number)
    if result == {"status": "insufficient_context"}:
        return result
    if (type(result) is not dict or set(result) != {"status", "metadata"}
            or result["status"] != "ok" or type(result["metadata"]) is not dict
            or set(result["metadata"]) != set(requested_fields)):
        raise ValueError("Invalid generated metadata")
    metadata = validate_metadata(result["metadata"])
    if "title" in metadata:
        forbidden = {safe_basename.casefold(), posixpath.splitext(safe_basename)[0].casefold(),
                     "file", "document", "report", "untitled", "delivery"}
        if cast(str, metadata["title"]).casefold() in forbidden:
            raise ValueError("Invalid generated metadata")
    if "description" in metadata:
        description = cast(str, metadata["description"])
        if content_mode == "history-only":
            prefix = "From delivery context only: "
            if not description.startswith(prefix):
                raise ValueError("Invalid generated metadata")
            description = description[len(prefix):]
        if not description or description.isspace():
            raise ValueError("Invalid generated metadata")
    if "tags" in metadata and not metadata["tags"]:
        raise ValueError("Invalid generated metadata")
    return {"status": "ok", "metadata": metadata}


def parse_generated(raw, requested_fields, content_mode, safe_basename):
    """Validate raw output without repair, coercion, persistence or provider calls.

    The caller must separately enforce finish reason, token cap and source authority.
    Fixed public errors do not constitute traceback-local memory zeroization.
    """
    if (type(requested_fields) is not tuple or not requested_fields
            or content_mode not in ("text", "image", "history-only")
            or type(safe_basename) is not str or not safe_basename
            or any(type(field) is not str or field not in ("title", "description", "tags")
                   for field in requested_fields)
            or tuple(sorted(set(requested_fields))) != requested_fields):
        raise ValueError("Invalid generation request")
    validate_metadata({})  # Pin the Unicode authority even for insufficient_context.
    try:
        return _parse(raw, requested_fields, content_mode, safe_basename)
    except (ValueError, RecursionError):
        pass
    # Outside the decoder handler: its exception must not be chained to the result.
    raise ValueError("Invalid generated metadata")
