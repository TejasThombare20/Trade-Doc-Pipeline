"""Helpers for turning Pydantic models into OpenAI JSON-schema payloads.

OpenAI structured outputs require the schema to declare all properties as
required and explicitly set additionalProperties=false. We walk the Pydantic
schema and enforce that recursively.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def openai_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema = _inline_refs(schema, schema)
    return _strictify(schema)


def _inline_refs(node: Any, root: dict) -> Any:
    """Replace every $ref with its referenced $defs entry, in place."""
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            # only local refs of the form "#/$defs/Name"
            name = ref.split("/")[-1]
            target = root.get("$defs", {}).get(name, {})
            return _inline_refs(dict(target), root)
        return {k: _inline_refs(v, root) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_refs(v, root) for v in node]
    return node


def _strictify(schema: dict) -> dict:
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        for v in props.values():
            _strictify(v)
        schema["required"] = list(props.keys())
        schema["additionalProperties"] = False
    if t == "array" and isinstance(schema.get("items"), dict):
        _strictify(schema["items"])
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            schema[key] = [_strictify(s) if isinstance(s, dict) else s for s in schema[key]]
    return schema
