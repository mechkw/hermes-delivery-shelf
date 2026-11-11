"""Presence-preserving metadata validation for the preservation service."""
import unicodedata

FIELDS = ("title", "description", "tags")


def _invalid(field, rule):
    raise ValueError(f"Invalid metadata: {field}/{rule}")


def _text(value, field, *, description=False):
    if type(value) is not str:
        _invalid(field, "type")
    limit = 4000 if description else 160 if field == "title" else 40
    if len(value) > limit or (not description and not value):
        _invalid(field, "scalar_limit")
    for char in value:
        code = ord(char)
        if description and char in "\n\t":
            continue
        if code < 32 or 127 <= code <= 159 or code in (0x2028, 0x2029) or 0xD800 <= code <= 0xDFFF:
            _invalid(field, "control")
    if not description:
        if value[0].isspace() or value[-1].isspace():
            _invalid(field, "edge_whitespace")
        if value.isspace():
            _invalid(field, "blank")


def validate_metadata(metadata, *, require_complete=False):
    """Return an independent JSON-shaped patch without changing bytes or presence.

    This validates supplied fields, not generated-output semantics or source authority.
    Callers still reject duplicate JSON keys before constructing this dictionary.
    """
    if unicodedata.unidata_version != "14.0.0":
        raise RuntimeError("Unicode 14 validation unavailable")
    if type(metadata) is not dict or any(key not in FIELDS for key in metadata):
        raise ValueError("Invalid metadata object")
    for field in FIELDS:
        if field not in metadata:
            continue
        value = metadata[field]
        if field == "tags":
            if type(value) is not list:
                _invalid(field, "type")
            if len(value) > 20:
                _invalid(field, "scalar_limit")
            seen = set()
            for index, tag in enumerate(value):
                label = f"tags[{index}]"
                _text(tag, label)
                key = tag.casefold()
                if key in seen:
                    _invalid(label, "duplicate")
                seen.add(key)
        else:
            _text(value, field, description=field == "description")
    if require_complete:
        for field in FIELDS:
            if field not in metadata:
                _invalid(field, "missing")
    return {field: list(value) if field == "tags" else value
            for field, value in metadata.items()}
