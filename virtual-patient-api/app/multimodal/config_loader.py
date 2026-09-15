"""Methodology configuration loader for the multimodal pipeline (Requirement 5).

Responsibilities:

* Load the three methodology YAML files (``processing.yaml``, ``thresholds.yaml``,
  ``label_rules.yaml``) once and cache the result for reuse (Requirement 5.1).
* Validate each file structurally against a minimal Pydantic config-shape
  schema and, on any failure, raise a :class:`ConfigError` that names the
  failing file and the reason (Requirement 5.2, 5.3).
* Expose the ``version`` string of each file as
  ``versions.processing`` / ``versions.thresholds`` / ``versions.label_rules``
  (Requirement 5.4).
* Compute a deterministic, order-independent ``config_hash`` over the effective
  merged methodology configuration (Requirement 5.5, 5.6).

Critical ``null`` semantics (Requirement 4.7): a methodology value that is
present in YAML but set to ``null`` is *preserved* as ``None`` so the pipeline
can later signal ``feature_unavailable`` for the dependent feature; it is never
replaced by an invented default. This is distinct from a *required structural
key being absent*, which is a misconfiguration and raises :class:`ConfigError`.

The config-shape models here are intentionally separate from the stage
contracts in ``schemas.py``: they validate the *shape of the configuration
files*, not the runtime pipeline data. They are deliberately permissive about
individual threshold values (which are provisional and may legitimately be
``null``) while being strict about the presence of the structural keys the
engines depend on.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

# Default directory holding the methodology YAML files, resolved relative to
# this module so packaging and working-directory changes do not break loading.
DEFAULT_CONFIG_DIR = Path(__file__).parent / "config"

_PROCESSING_FILE = "processing.yaml"
_THRESHOLDS_FILE = "thresholds.yaml"
_LABEL_RULES_FILE = "label_rules.yaml"


class ConfigError(Exception):
    """Raised when a methodology config file is missing, unloadable, or invalid.

    The message always identifies the failing file so a misconfiguration fails
    clearly and points at the file to fix (Requirement 5.3).
    """


# ---------------------------------------------------------------------------
# Config-shape validation models
#
# These validate the structural shape of each YAML file. They intentionally do
# NOT constrain provisional threshold values, which may be numeric or an
# explicit ``null`` (preserved as feature_unavailable). Required structural keys
# that the engines depend on are declared as required fields; a present-``null``
# leaf is allowed and preserved, while an absent required key raises.
# ---------------------------------------------------------------------------


class _ProcessingParaverbal(BaseModel):
    model_config = ConfigDict(extra="allow")

    min_pause_ms: int | None


class _ProcessingNonverbal(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Only the top-level presence of these sub-sections is required; the
    # individual leaf values (tolerances, thresholds, nod params) may be null.
    gaze: dict[str, Any]
    smile: dict[str, Any]
    nod: dict[str, Any]


class _ProcessingConfig(BaseModel):
    """Structural shape of ``processing.yaml``."""

    model_config = ConfigDict(extra="allow")

    version: str
    paraverbal: _ProcessingParaverbal
    nonverbal: _ProcessingNonverbal


class _ThresholdsConfig(BaseModel):
    """Structural shape of ``thresholds.yaml``.

    The per-family strategy tables are kept as opaque dicts here: the threshold
    engine owns strategy validation. This loader only guarantees the required
    top-level structure exists and the guard is present.
    """

    model_config = ConfigDict(extra="allow")

    version: str
    min_turns_for_session_stats: int
    paraverbal: dict[str, Any]
    nonverbal: dict[str, Any]


class _LabelRulesConfig(BaseModel):
    """Structural shape of ``label_rules.yaml``.

    The per-family rule lists are kept as opaque dicts here: the label engine
    owns rule-grammar validation. This loader only guarantees the required
    top-level structure exists.
    """

    model_config = ConfigDict(extra="allow")

    version: str
    families: dict[str, Any]


# ---------------------------------------------------------------------------
# Public accessor
# ---------------------------------------------------------------------------


class Versions(BaseModel):
    """Methodology config versions exposed on every result (Requirement 5.4)."""

    processing: str
    thresholds: str
    label_rules: str


class MethodologyConfig(BaseModel):
    """Effective, validated methodology configuration.

    Exposes the raw parsed sections (so downstream engines read structured
    config rather than re-parsing YAML), the per-file ``versions``, and the
    deterministic ``config_hash``. Present-``null`` methodology values are
    preserved inside the raw sections and must be interpreted by the engines as
    ``feature_unavailable`` (Requirement 4.7).
    """

    model_config = ConfigDict(frozen=True)

    processing: dict[str, Any]
    thresholds: dict[str, Any]
    label_rules: dict[str, Any]
    versions: Versions
    config_hash: str


# ---------------------------------------------------------------------------
# Loading, validation, and hashing
# ---------------------------------------------------------------------------


def _read_yaml(config_dir: Path, filename: str) -> dict[str, Any]:
    """Read and parse one YAML file, raising a clear ConfigError on failure."""

    path = config_dir / filename
    if not path.is_file():
        raise ConfigError(f"missing config file: {path}")
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem-dependent
        raise ConfigError(f"unable to read config file {path}: {exc}") from exc
    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in config file {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ConfigError(
            f"invalid config file {path}: expected a mapping at the top level, "
            f"got {type(parsed).__name__}"
        )
    return parsed


def _validate(model: type[BaseModel], data: dict[str, Any], path: Path) -> None:
    """Validate a parsed config dict against its shape model.

    Only the structural shape is validated; the parsed dict itself (with any
    present-``null`` values intact) is what the pipeline uses, so validation
    never rewrites or defaults the methodology values.
    """

    try:
        model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid config: {path}: {exc}") from exc


def _canonical_json(data: Any) -> str:
    """Serialize config to canonical JSON: sorted keys, stable separators.

    Sorting keys makes the serialization independent of YAML key order, so two
    effective configurations that differ only in key ordering hash identically
    (Requirement 5.6).
    """

    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _compute_config_hash(
    processing: dict[str, Any],
    thresholds: dict[str, Any],
    label_rules: dict[str, Any],
) -> str:
    """Compute the deterministic SHA-256 config hash over the merged config.

    The hash covers the effective methodology content only (the three parsed
    documents), never file paths or timestamps, so identical effective config
    always yields an identical hash (Requirement 5.5, 5.6, 6.3).
    """

    effective = {
        "processing": processing,
        "thresholds": thresholds,
        "label_rules": label_rules,
    }
    canonical = _canonical_json(effective)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_methodology_config(config_dir: Path) -> MethodologyConfig:
    """Load, validate, and assemble the methodology config from ``config_dir``."""

    processing_path = config_dir / _PROCESSING_FILE
    thresholds_path = config_dir / _THRESHOLDS_FILE
    label_rules_path = config_dir / _LABEL_RULES_FILE

    processing = _read_yaml(config_dir, _PROCESSING_FILE)
    thresholds = _read_yaml(config_dir, _THRESHOLDS_FILE)
    label_rules = _read_yaml(config_dir, _LABEL_RULES_FILE)

    _validate(_ProcessingConfig, processing, processing_path)
    _validate(_ThresholdsConfig, thresholds, thresholds_path)
    _validate(_LabelRulesConfig, label_rules, label_rules_path)

    versions = Versions(
        processing=processing["version"],
        thresholds=thresholds["version"],
        label_rules=label_rules["version"],
    )
    config_hash = _compute_config_hash(processing, thresholds, label_rules)

    return MethodologyConfig(
        processing=processing,
        thresholds=thresholds,
        label_rules=label_rules,
        versions=versions,
        config_hash=config_hash,
    )


@lru_cache(maxsize=None)
def _load_cached(config_dir_str: str) -> MethodologyConfig:
    """Cached loader keyed by the resolved config directory string.

    The cache key is the resolved directory path so that the default directory
    and any test-supplied directory each cache independently. Use
    :func:`reload_methodology_config` to clear the cache in tests.
    """

    return _load_methodology_config(Path(config_dir_str))


def load_methodology_config(config_dir: Path | str | None = None) -> MethodologyConfig:
    """Return the cached methodology config, loading it on first use.

    Args:
        config_dir: Optional override for the config directory (used by tests).
            Defaults to the ``config/`` directory beside this module.

    Raises:
        ConfigError: If any config file is missing, unloadable, or invalid.
    """

    resolved = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    return _load_cached(str(resolved.resolve()))


def reload_methodology_config(
    config_dir: Path | str | None = None,
) -> MethodologyConfig:
    """Clear the load cache and reload the methodology config.

    Provided so tests can force a fresh load after changing config on disk
    without leaking cached state between cases (Requirement 5.1 support).
    """

    _load_cached.cache_clear()
    return load_methodology_config(config_dir)
