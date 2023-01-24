from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import ujson
from deepdiff.model import PrettyOrderedSet


class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (frozenset, set, PrettyOrderedSet)):
            return list(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S %Z")
        if isinstance(obj, Exception):
            return str(obj)
        if isinstance(obj, UUID):
            return str(obj)
        return json.JSONEncoder.default(self, obj)


def dumps(
    obj: any,
    ensure_ascii: bool = True,
    double_precision: int = 9,
    encode_html_chars: bool = False,
    escape_forward_slashes: bool = False,
    sort_keys: bool = False,
    indent: int = 0,
    **kwargs,
) -> str:
    # Try fast "ujson is 3x faster than the standard json library" first
    try:
        result = ujson.dumps(
            obj,
            ensure_ascii=ensure_ascii,
            double_precision=double_precision,
            encode_html_chars=encode_html_chars,
            escape_forward_slashes=escape_forward_slashes,
            sort_keys=sort_keys,
            indent=indent,
            **kwargs,
        )
    except TypeError:
        result = json.dumps(
            obj,
            cls=SetEncoder,
            ensure_ascii=ensure_ascii,
            sort_keys=sort_keys,
            indent=indent,
            **kwargs,
        )
    return result


def loads(s: str, **kwargs) -> Any:
    try:
        result = ujson.loads(s, **kwargs)
    except ValueError:
        result = json.loads(s, **kwargs)
    return result
