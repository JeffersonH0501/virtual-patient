"""Choose the Tavus face for a patient from gender, age and personality."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

logger = logging.getLogger(__name__)

YOUNG_MAX_AGE = 39
ADULT_MAX_AGE = 64


def age_group(age: int | None) -> str | None:
    """Return `young` (<40), `adult` (40-64) or `senior` (65+)."""
    if age is None or age < 0:
        return None
    if age <= YOUNG_MAX_AGE:
        return "young"
    if age <= ADULT_MAX_AGE:
        return "adult"
    return "senior"


def parse_face_map(raw: str | None) -> dict[str, str]:
    """Parse the `TAVUS_FACE_MAP` JSON object; invalid input yields an empty map."""
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("tavus_face_map_invalid reason=not_json")
        return {}
    if not isinstance(data, dict):
        logger.warning("tavus_face_map_invalid reason=not_object")
        return {}
    return {
        str(key).strip().lower(): str(value).strip()
        for key, value in data.items()
        if str(value).strip()
    }


def select_face_id(
    face_map: Mapping[str, str],
    gender: str | None,
    age: int | None,
    personality_key: str | None,
) -> str | None:
    """Return the most specific configured face, or None when nothing matches.

    Keys are tried from most to least specific:
    `gender:age_group:personality`, `gender:age_group`, `gender:personality`
    and `gender`.
    """
    if not face_map or not gender:
        return None
    group = age_group(age)
    personality = (personality_key or "").strip().lower() or None
    candidates = []
    if group and personality:
        candidates.append(f"{gender}:{group}:{personality}")
    if group:
        candidates.append(f"{gender}:{group}")
    if personality:
        candidates.append(f"{gender}:{personality}")
    candidates.append(gender)
    for key in candidates:
        if key in face_map:
            return face_map[key]
    return None
