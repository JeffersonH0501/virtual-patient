"""Tests for the methodology config loader (Requirements 28.1, 5.2, 5.3, 5.6).

These tests exercise the public API of ``app.multimodal.config_loader``:

* ``load_methodology_config`` / ``reload_methodology_config`` for load + caching,
* ``ConfigError`` for malformed / missing / non-mapping config, and
* ``MethodologyConfig`` (``.processing`` / ``.thresholds`` / ``.label_rules`` /
  ``.versions`` / ``.config_hash``).

Every case that touches the cache clears it (via ``reload_methodology_config``)
so cases stay isolated. Temporary config directories are built with the
``tmp_path`` fixture; the real bundled config is loaded only for the happy path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from app.multimodal.config_loader import (
    DEFAULT_CONFIG_DIR,
    ConfigError,
    MethodologyConfig,
    load_methodology_config,
    reload_methodology_config,
)

_PROCESSING_FILE = "processing.yaml"
_THRESHOLDS_FILE = "thresholds.yaml"
_LABEL_RULES_FILE = "label_rules.yaml"


# ---------------------------------------------------------------------------
# Fixtures / helpers to build minimal but structurally valid temp config dirs
# ---------------------------------------------------------------------------


def _valid_processing() -> dict[str, Any]:
    """A minimal structurally valid processing config.

    Keeps ``gaze.alignment_tolerance_radians`` present-but-null so the
    present-null preservation case can rely on this baseline.
    """

    return {
        "version": "processing_v1",
        "paraverbal": {
            "min_pause_ms": 250,
            "min_voiced_duration_ms": 300,
        },
        "nonverbal": {
            "sample_fps": 2,
            "gaze": {"alignment_tolerance_radians": None},
            "smile": {"au12_active_threshold": None},
            "nod": {"enabled": True, "min_amplitude_deg": None},
        },
    }


def _valid_thresholds() -> dict[str, Any]:
    """A minimal structurally valid thresholds config."""

    return {
        "version": "thresholds_v1",
        "min_turns_for_session_stats": 4,
        "paraverbal": {
            "temporal": {
                "speech_rate_wpm": {
                    "strategy": "fixed_bands",
                    "low_below": 110,
                    "high_above": 170,
                    "labels": ["low", "typical", "high"],
                }
            }
        },
        "nonverbal": {
            "visual_orientation": {
                "visual_alignment_ratio": {
                    "strategy": "fixed_bands",
                    "low_below": 0.30,
                    "high_above": 0.65,
                    "labels": ["low", "typical", "high"],
                }
            }
        },
    }


def _valid_label_rules() -> dict[str, Any]:
    """A minimal structurally valid label_rules config."""

    return {
        "version": "label_rules_v1",
        "families": {
            "temporal": {
                "rules": [
                    {"value": "typical", "all": {"global_rate": "typical"}},
                ],
                "fallback": "mixed",
                "unavailable": "unavailable",
            }
        },
    }


def _write_config_dir(
    directory: Path,
    *,
    processing: dict[str, Any] | None = None,
    thresholds: dict[str, Any] | None = None,
    label_rules: dict[str, Any] | None = None,
) -> Path:
    """Write the three methodology YAML files into ``directory``.

    Any section left as ``None`` falls back to its valid baseline, so a case
    only has to override the file it wants to break.
    """

    directory.mkdir(parents=True, exist_ok=True)
    (directory / _PROCESSING_FILE).write_text(
        yaml.safe_dump(processing if processing is not None else _valid_processing()),
        encoding="utf-8",
    )
    (directory / _THRESHOLDS_FILE).write_text(
        yaml.safe_dump(thresholds if thresholds is not None else _valid_thresholds()),
        encoding="utf-8",
    )
    (directory / _LABEL_RULES_FILE).write_text(
        yaml.safe_dump(
            label_rules if label_rules is not None else _valid_label_rules()
        ),
        encoding="utf-8",
    )
    return directory


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    """Clear the loader cache before and after every test for isolation.

    The loader caches by resolved directory, so clearing the underlying cache
    keeps each case independent even when two cases reuse the same tmp path.
    """

    from app.multimodal import config_loader

    config_loader._load_cached.cache_clear()
    yield
    config_loader._load_cached.cache_clear()


# ---------------------------------------------------------------------------
# Successful load of the real bundled config
# ---------------------------------------------------------------------------


def test_load_real_config_exposes_expected_versions_and_hash() -> None:
    """The bundled config loads and exposes the documented versions/hash."""

    config = load_methodology_config()

    assert isinstance(config, MethodologyConfig)
    # Versions come from the real bundled files.
    assert config.versions.processing == "processing_v1"
    assert config.versions.thresholds == "thresholds_v1"
    assert config.versions.label_rules == "label_rules_v1"
    # Sections are parsed mappings.
    assert isinstance(config.processing, dict)
    assert isinstance(config.thresholds, dict)
    assert isinstance(config.label_rules, dict)
    # config_hash is a non-empty lowercase hex string (SHA-256 -> 64 chars).
    assert isinstance(config.config_hash, str)
    assert config.config_hash != ""
    assert len(config.config_hash) == 64
    int(config.config_hash, 16)  # raises ValueError if not valid hex


def test_default_config_dir_points_at_bundled_config() -> None:
    """Sanity check that the default config directory holds the three files."""

    assert (DEFAULT_CONFIG_DIR / _PROCESSING_FILE).is_file()
    assert (DEFAULT_CONFIG_DIR / _THRESHOLDS_FILE).is_file()
    assert (DEFAULT_CONFIG_DIR / _LABEL_RULES_FILE).is_file()


# ---------------------------------------------------------------------------
# Caching behavior
# ---------------------------------------------------------------------------


def test_repeated_load_returns_cached_object(tmp_path: Path) -> None:
    """Two loads of the same dir return the same cached instance."""

    config_dir = _write_config_dir(tmp_path / "cfg")

    first = load_methodology_config(config_dir=config_dir)
    second = load_methodology_config(config_dir=config_dir)

    assert first is second


def test_reload_forces_fresh_load(tmp_path: Path) -> None:
    """reload_methodology_config clears the cache and reflects disk changes."""

    config_dir = _write_config_dir(tmp_path / "cfg")

    first = load_methodology_config(config_dir=config_dir)

    # Change the version on disk, then reload; the cache must not be reused.
    changed = _valid_processing()
    changed["version"] = "processing_v1_reloaded"
    _write_config_dir(tmp_path / "cfg", processing=changed)

    reloaded = reload_methodology_config(config_dir=config_dir)

    assert reloaded is not first
    assert first.versions.processing == "processing_v1"
    assert reloaded.versions.processing == "processing_v1_reloaded"


# ---------------------------------------------------------------------------
# Malformed config raises ConfigError naming the failing file
# ---------------------------------------------------------------------------


def test_invalid_yaml_syntax_raises_config_error_naming_file(
    tmp_path: Path,
) -> None:
    """(a) Syntactically invalid YAML raises ConfigError naming the file."""

    config_dir = _write_config_dir(tmp_path / "cfg")
    # Overwrite thresholds.yaml with broken YAML (unbalanced brackets).
    (config_dir / _THRESHOLDS_FILE).write_text(
        "version: thresholds_v1\nparaverbal: [unclosed\n", encoding="utf-8"
    )

    with pytest.raises(ConfigError) as excinfo:
        load_methodology_config(config_dir=config_dir)

    assert _THRESHOLDS_FILE in str(excinfo.value)


def test_missing_required_file_raises_config_error_naming_file(
    tmp_path: Path,
) -> None:
    """(b) A missing required file raises ConfigError naming the file."""

    config_dir = _write_config_dir(tmp_path / "cfg")
    (config_dir / _LABEL_RULES_FILE).unlink()

    with pytest.raises(ConfigError) as excinfo:
        load_methodology_config(config_dir=config_dir)

    assert _LABEL_RULES_FILE in str(excinfo.value)


def test_missing_required_structural_key_raises_config_error_naming_file(
    tmp_path: Path,
) -> None:
    """(c) A missing required structural key raises ConfigError naming file."""

    processing = _valid_processing()
    # Remove a required leaf that the shape model declares.
    del processing["paraverbal"]["min_pause_ms"]
    config_dir = _write_config_dir(tmp_path / "cfg", processing=processing)

    with pytest.raises(ConfigError) as excinfo:
        load_methodology_config(config_dir=config_dir)

    message = str(excinfo.value)
    assert _PROCESSING_FILE in message


def test_non_mapping_top_level_raises_config_error_naming_file(
    tmp_path: Path,
) -> None:
    """(d) A non-mapping top level raises ConfigError naming the file."""

    config_dir = _write_config_dir(tmp_path / "cfg")
    # A YAML list at the top level is valid YAML but not a mapping.
    (config_dir / _PROCESSING_FILE).write_text(
        "- one\n- two\n", encoding="utf-8"
    )

    with pytest.raises(ConfigError) as excinfo:
        load_methodology_config(config_dir=config_dir)

    assert _PROCESSING_FILE in str(excinfo.value)


# ---------------------------------------------------------------------------
# config_hash determinism
# ---------------------------------------------------------------------------


def test_config_hash_stable_across_reloads_of_same_config(tmp_path: Path) -> None:
    """Same effective config -> same hash across independent reloads."""

    config_dir = _write_config_dir(tmp_path / "cfg")

    first = load_methodology_config(config_dir=config_dir)
    first_hash = first.config_hash

    reloaded = reload_methodology_config(config_dir=config_dir)

    assert reloaded.config_hash == first_hash


def test_config_hash_ignores_yaml_key_ordering(tmp_path: Path) -> None:
    """Key reordering in the YAML yields an identical config_hash."""

    ordered = _valid_processing()
    # Build a reordered variant with the same effective content: reverse the
    # top-level key order and reorder a nested mapping. safe_dump(sort_keys=...)
    # controls serialization order on disk without changing meaning.
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()

    (dir_a / _PROCESSING_FILE).write_text(
        yaml.safe_dump(ordered, sort_keys=False), encoding="utf-8"
    )
    (dir_b / _PROCESSING_FILE).write_text(
        yaml.safe_dump(ordered, sort_keys=True), encoding="utf-8"
    )
    for directory in (dir_a, dir_b):
        (directory / _THRESHOLDS_FILE).write_text(
            yaml.safe_dump(_valid_thresholds(), sort_keys=False),
            encoding="utf-8",
        )
        (directory / _LABEL_RULES_FILE).write_text(
            yaml.safe_dump(_valid_label_rules(), sort_keys=True),
            encoding="utf-8",
        )

    config_a = load_methodology_config(config_dir=dir_a)
    reload_methodology_config(config_dir=dir_b)
    config_b = load_methodology_config(config_dir=dir_b)

    assert config_a.config_hash == config_b.config_hash


def test_config_hash_changes_when_content_changes(tmp_path: Path) -> None:
    """A genuine content change produces a different hash (guards the above)."""

    base_dir = _write_config_dir(tmp_path / "base")
    changed = _valid_processing()
    changed["paraverbal"]["min_pause_ms"] = 999
    changed_dir = _write_config_dir(tmp_path / "changed", processing=changed)

    base = load_methodology_config(config_dir=base_dir)
    reload_methodology_config(config_dir=changed_dir)
    changed_config = load_methodology_config(config_dir=changed_dir)

    assert base.config_hash != changed_config.config_hash


# ---------------------------------------------------------------------------
# Present-null preservation
# ---------------------------------------------------------------------------


def test_present_null_value_is_preserved_as_none(tmp_path: Path) -> None:
    """gaze.alignment_tolerance_radians: null loads as None, not a default."""

    processing = _valid_processing()
    processing["nonverbal"]["gaze"]["alignment_tolerance_radians"] = None
    config_dir = _write_config_dir(tmp_path / "cfg", processing=processing)

    config = load_methodology_config(config_dir=config_dir)

    gaze = config.processing["nonverbal"]["gaze"]
    assert "alignment_tolerance_radians" in gaze
    assert gaze["alignment_tolerance_radians"] is None
