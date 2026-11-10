from app.core.functional_config import read_config_json


_CRITERIA_COUNTS = {
    "general_communication": 7,
    "show_interest": 4,
    "show_empathy": 6,
    "speak_clearly": 4,
    "open_communication": 3,
    "completeness": 8,
}
_RUBRIC = read_config_json("rubrics/evaluation.json")
if (
    not isinstance(_RUBRIC, dict)
    or _RUBRIC.keys() != {"human_rating_version", "en", "es"}
    or not isinstance(_RUBRIC["human_rating_version"], str)
    or not 1 <= len(_RUBRIC["human_rating_version"]) <= 80
):
    raise ValueError("Invalid evaluation rubric metadata")

for _locale in ("en", "es"):
    _criteria = _RUBRIC[_locale]
    if not isinstance(_criteria, dict) or tuple(_criteria) != tuple(_CRITERIA_COUNTS):
        raise ValueError(f"Invalid rubric categories for {_locale}")
    for _category, _count in _CRITERIA_COUNTS.items():
        _items = _criteria[_category]
        if not isinstance(_items, list) or len(_items) != _count or not all(
            isinstance(item, str) and item.strip() for item in _items
        ):
            raise ValueError(f"Invalid rubric criteria for {_locale}/{_category}")

HUMAN_RATING_RUBRIC_VERSION = _RUBRIC["human_rating_version"]
EVALUATION_ASPECTS = _RUBRIC["en"]
EVALUATION_ASPECTS_ES = _RUBRIC["es"]


def get_aspects_for_category(category: str) -> list:
    """Get evaluation aspects for a specific category and language"""
    return EVALUATION_ASPECTS.get(category, [])

def get_all_aspects(language: str = "en") -> dict:
    """Get all evaluation aspects for a specific language"""
    if language == "es":
        return EVALUATION_ASPECTS_ES
    return EVALUATION_ASPECTS

def format_aspects_for_prompt(category: str, numbered: bool = True) -> str:
    """Helper function to format aspects for prompts"""
    aspects = get_aspects_for_category(category)
    if numbered:
        return "\n".join([f"{i+1}. {aspect}" for i, aspect in enumerate(aspects)])
    else:
        return "\n".join([f"- {aspect}" for aspect in aspects])
