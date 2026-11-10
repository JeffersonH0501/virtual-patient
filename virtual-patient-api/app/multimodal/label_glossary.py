"""Observational descriptions of integrated labels."""

from pydantic import TypeAdapter

from app.core.functional_config import read_config_yaml


LABEL_GLOSSARY = TypeAdapter(dict[str, str]).validate_python(
    read_config_yaml("labels/glossary.yaml"), strict=True,
)
