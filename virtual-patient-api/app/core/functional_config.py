"""Read functional configuration shipped with the backend."""

import json
import re
from functools import lru_cache
from pathlib import Path
from string import Formatter

import yaml


CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"


def read_config_json(name: str):
    path = CONFIG_ROOT / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot load configuration {path}: {exc}") from exc


def read_config_yaml(name: str):
    path = CONFIG_ROOT / name
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot load configuration {path}: {exc}") from exc


@lru_cache(maxsize=None)
def load_prompt(name: str, *fields: str, double_braces: bool = False) -> str:
    path = CONFIG_ROOT / "prompts" / f"{name}.txt"
    try:
        template = path.read_text(encoding="utf-8")
        if double_braces:
            placeholders = set(re.findall(r"\{\{(\w+)\}\}", template))
        elif fields:
            parsed = [(field, spec, conversion) for _, field, spec, conversion in
                      Formatter().parse(template) if field is not None]
            if any(spec or conversion for _, spec, conversion in parsed):
                raise ValueError("placeholder formatting and conversions are unsupported")
            placeholders = {field for field, _, _ in parsed}
        else:
            placeholders = set()
        if placeholders != set(fields):
            raise ValueError(f"expected placeholders {', '.join(fields)}")
        if not template.strip():
            raise ValueError("template is empty")
        return template
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot load prompt {path}: {exc}") from exc


def render_prompt(name: str, **values) -> str:
    return load_prompt(name, *values).format(**values)
