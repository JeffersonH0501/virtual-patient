#!/usr/bin/env bash
# Enumerate configured label combinations, without retuning thresholds.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
docker compose -f docker-compose.local.yml run --rm --no-deps -T api python - <<'PY'
import itertools
import json
from collections import Counter
from app.multimodal.config_loader import load_methodology_config
from app.multimodal.label_engine import _SLOT_TO_FEATURE, _rule_matches
from app.multimodal.schemas import FamilyLabel
config = load_methodology_config()
for family, specification in config.label_rules['families'].items():
    domain = 'nonverbal' if family in config.thresholds['nonverbal'] else 'paraverbal'
    features = config.thresholds[domain][family]
    keys, choices = [], []
    for name, feature in features.items():
        keys.append(name)
        choices.append(feature.get('labels', ['speaking', 'listening']))
    winners = Counter()
    overlaps = 0
    for values in itertools.product(*choices):
        base = {key: FamilyLabel(status='ok', value=value) for key, value in zip(keys, values)}
        matches = [rule['value'] for rule in specification['rules'] if _rule_matches(family, rule, base, {})]
        overlaps += len(matches) > 1
        winners[matches[0] if matches else specification['fallback']] += 1
    unreachable = [rule['value'] for rule in specification['rules'] if not winners[rule['value']]]
    print(json.dumps({'family': family, 'combinations': sum(winners.values()), 'overlappingRuleCombinations': overlaps,
                      'unreachableRuleValues': unreachable, 'firstMatchCounts': dict(winners)}))
PY
