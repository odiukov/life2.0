"""Flattened environment variable names of a settings model for docs and checks."""

from __future__ import annotations

import typing
from enum import Enum

from pydantic import BaseModel
from pydantic_settings import NoDecode


def _names(model: type[BaseModel], prefix: str, exclude: set[str]) -> set[str]:
    out: set[str] = set()
    for field_name, field in model.model_fields.items():
        if field_name in exclude:
            continue
        name = f"{prefix}{field_name.upper()}"
        annotation = field.annotation
        origin = typing.get_origin(annotation)
        if NoDecode in field.metadata:
            out.add(name)
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
            out |= _names(annotation, f"{name}__", set())
        elif origin is dict:
            key_type = typing.get_args(annotation)[0]
            if isinstance(key_type, type) and issubclass(key_type, Enum):
                out |= {f"{name}__{member.name}" for member in key_type}
            else:
                out.add(f"{name}__<KEY>")
        else:
            out.add(name)
    return out


def env_names(
    model: type[BaseModel], *, exclude: set[str] | frozenset[str] = frozenset()
) -> set[str]:
    return _names(model, "", set(exclude))
