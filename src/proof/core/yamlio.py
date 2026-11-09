"""Strict YAML loading for rule packs, provider files and review records.

Based on PyYAML's ``SafeLoader`` (no object construction) with four restrictions:
- duplicate mapping keys are errors;
- aliases are errors, which rules out expansion bombs and hidden sharing;
- mapping keys must be strings;
- only ``true`` / ``false`` are booleans, so YAML 1.1 words such as ``yes``, ``no``, ``on`` and ``off`` stay strings.
Files are limited in size and must be UTF-8.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from yaml.resolver import BaseResolver

DEFAULT_MAX_BYTES = 5 * 1024 * 1024

_BOOL_TAG = "tag:yaml.org,2002:bool"
_BOOL_PATTERN = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")


class YamlError(ValueError):
    """A YAML document violates the strict loading rules."""


class _StrictLoader(yaml.SafeLoader):
    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise YamlError(f"aliases are not allowed (line {event.start_mark.line + 1})")
        return super().compose_node(parent, index)


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    if not isinstance(node, yaml.MappingNode):  # pragma: no cover - guarded by the resolver
        raise YamlError("expected a mapping")
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            raise YamlError(f"merge keys are not allowed (line {key_node.start_mark.line + 1})")
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str):
            raise YamlError(f"mapping key {key!r} is not a string (line {key_node.start_mark.line + 1})")
        if key in mapping:
            raise YamlError(f"duplicate key {key!r} (line {key_node.start_mark.line + 1})")
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


def _strict_bool_resolvers() -> dict[str, list[tuple[str, re.Pattern[str]]]]:
    resolvers = {
        first: [(tag, pattern) for tag, pattern in entries if tag != _BOOL_TAG]
        for first, entries in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    for first in "tTfF":
        resolvers.setdefault(first, []).append((_BOOL_TAG, _BOOL_PATTERN))
    return resolvers


_StrictLoader.yaml_implicit_resolvers = _strict_bool_resolvers()
_StrictLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_text(text: str, *, source: str = "<string>") -> Any:
    """Parse one YAML document with the strict rules."""
    try:
        return yaml.load(text, Loader=_StrictLoader)  # noqa: S506 - _StrictLoader derives from SafeLoader
    except YamlError as exc:
        raise YamlError(f"{source}: {exc}") from None
    except yaml.YAMLError as exc:
        raise YamlError(f"{source}: {exc}") from None


def load_file(path: str | Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> Any:
    """Read and parse a UTF-8 YAML file no larger than ``max_bytes``."""
    path = Path(path)
    size = path.stat().st_size
    if size > max_bytes:
        raise YamlError(f"{path}: file has {size} bytes, limit is {max_bytes}")
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise YamlError(f"{path}: not valid UTF-8 ({exc})") from None
    return load_text(text, source=str(path))


class _PlainDumper(yaml.SafeDumper):
    """Writes every object in full; the strict loader rejects aliases."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


def dump_text(data: Any, *, comment: str | None = None) -> str:
    """YAML text of ``data`` with keys in the given order, Unicode as is, and an optional comment block on top."""
    body = yaml.dump(data, Dumper=_PlainDumper, allow_unicode=True, sort_keys=False, width=120)
    if comment is None:
        return body
    header = "".join(f"# {line}".rstrip() + "\n" for line in comment.split("\n"))
    return header + body
