from app.paraverbal.opensmile_extractor import _temporal_interpretability


def test_temporal_interpretability_applies_versioned_initial_thresholds():
    result = _temporal_interpretability({
        "speaking_rate_wpm": 105.0,
        "articulation_rate_wpm": 155.0,
        "pause_count": 4,
        "pause_total_ms": 4200,
        "pause_median_ms": 1250.0,
        "pause_ratio": 0.32,
    }, turn_duration_ms=30_000)

    temporal = result["acoustic_temporal"]
    assert temporal["raw"]["speaking_rate_wpm"] == 105.0
    assert temporal["derived"]["rate_gap_wpm"] == 50.0
    assert temporal["derived"]["pause_frequency_per_min"] == 8.0
    assert temporal["labels"]["status"] == "provisional"
    assert temporal["labels"]["values"] == {
        "global_rate": "ritmo_global_bajo",
        "articulation": "articulacion_tipica",
        "pause_load": "carga_pausas_alta",
        "pause_duration": "pausas_predominantemente_largas",
        "pause_frequency": "frecuencia_pausas_tipica",
        "temporal_profile": "ritmo_reducido_por_pausas",
    }
    assert temporal["calibration"]["version"] == "temporal_initial_v1"
    assert "communication_quality" in temporal["scope"]["does_not_infer"]


def test_temporal_interpretability_uses_inclusive_typical_boundaries():
    result = _temporal_interpretability({
        "speaking_rate_wpm": 170.0,
        "articulation_rate_wpm": 130.0,
        "pause_count": 6,
        "pause_total_ms": 4500,
        "pause_median_ms": 500.0,
        "pause_ratio": 0.15,
    }, turn_duration_ms=60_000)

    assert result["acoustic_temporal"]["labels"]["values"] == {
        "global_rate": "ritmo_global_tipico",
        "articulation": "articulacion_tipica",
        "pause_load": "carga_pausas_tipica",
        "pause_duration": "pausas_duracion_tipica",
        "pause_frequency": "frecuencia_pausas_tipica",
        "temporal_profile": "patron_temporal_tipico",
    }


def test_temporal_interpretability_builds_fast_bursts_profile():
    result = _temporal_interpretability({
        "speaking_rate_wpm": 125.0,
        "articulation_rate_wpm": 195.0,
        "pause_count": 8,
        "pause_total_ms": 9200,
        "pause_median_ms": 720.0,
        "pause_ratio": 0.34,
    }, turn_duration_ms=30_000)

    values = result["acoustic_temporal"]["labels"]["values"]
    assert values["temporal_profile"] == "rafagas_rapidas_con_pausas"
