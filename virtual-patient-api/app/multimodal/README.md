# Multimodal pipeline (`app/multimodal/`)

This module owns the staged, versioned multimodal pipeline that turns a
finalized interview recording into per-turn, per-family descriptive
observations. It coordinates the existing paraverbal (OpenSMILE) and nonverbal
(Py-Feat) extractors, derives processed features, applies declarative
thresholds, and produces one integrated label per family — or an explicit
unavailable/insufficient outcome when data is missing.

## Descriptive-only disclaimer

**These thresholds are descriptive/provisional research thresholds and are not
clinical diagnostic or psychological cutoffs.** Every numeric default in the
configuration files is a provisional research value chosen to describe
behavioral and contextual observations; none has been clinically validated.

The pipeline is **descriptive-only**. It records behavioral and contextual
observations (how fast someone spoke, how often they paused, whether gaze was
aligned with a calibrated interaction center, whether a nod occurred, whether
AU12 was active). It does **not** infer emotion, empathy, attention, warmth, or
communicative quality, and it produces no low-level psychological labels such as
`warm`, `tense`, `attentive`, or `distracted`. Absent or low-quality evidence is
represented as `unavailable` / `insufficient_reference_data` with a reason, never
as negative performance and never as a fabricated number.

## Maturity of what is described here

Following the project's `existing` / `designed` / `planned` / `validated`
distinction:

- **Existing**: the staged pipeline, the two extractors (reduced to extraction +
  quality only), the derivation/threshold/label stages, the personal-baseline
  calibration flow, layered per-turn persistence, the legacy read adapter, and
  the relabeling script — all described below and present in this module.
- **Designed / planned**: several methodology values are intentionally left
  `null` in the config (gaze alignment tolerance, AU12 active threshold, nod
  detector parameters, some band edges). While `null`, the dependent feature is
  reported as `feature_unavailable`; the detector shapes exist but their
  thresholds await methodology input.
- **No late fusion is implemented.** The pipeline stops at per-turn integrated
  labels. There is no interview-level aggregation and no cross-modal or
  text+multimodal late fusion. The hand-off point after the labeling stage only
  *prepares* the downstream recording → multimodal → text-evaluation →
  late-fusion → feedback-coherence sequence; none of that scoring exists here.
- **Validated**: none of the thresholds are empirically or expert-validated.

## Staged flow

```
Calibration ─► Extraction ─► Preprocessing ─► Thresholding ─► Base labels ─► Label rules ─► Integrated labels
```

```
[CALIBRATION]  calibration.py
   PersonalBaseline (numeric only, F0 in semitones)
   read from interview_metadata.calibration.personal_baseline
        │
[EXTRACTION]  extractors (signal + quality only, NO labels)
   ├─ OpenSMILE_Extractor  ─► ParaverbalRawFeatures   (student-speaking turns only)
   └─ PyFeat_Extractor     ─► NonverbalRawFeatures    (all turn windows)
        │
[PREPROCESSING]  per-modality derivation
   ├─ app/paraverbal/preprocessing.py  ─► ParaverbalProcessedFeatures
   └─ app/nonverbal/preprocessing.py   ─► NonverbalProcessedFeatures
        │
[SESSION REFERENCES]  computed once per interview (two-pass, guarded)
        │
[THRESHOLDING]  threshold_engine.py + thresholds.yaml  ─► Base labels (per feature)
        │
[LABEL RULES]  label_engine.py + label_rules.yaml
   IntegratedLabels: exactly one per available family, else unavailable + reason
        │
[PERSIST]  MultimodalTurnResult ─► interview_turns.paraverbal / .nonverbal_features
           (+ observation_processing lifecycle updates)
```

## The six label families

Each family yields **exactly one** integrated label when data is available;
otherwise it yields `unavailable` or `insufficient_reference_data` with a reason.

Paraverbal (student-speaking turns only):

- `temporal` — global speech rate, articulation rate, pause load, pause
  duration, pause frequency (fixed bands).
- `prosodic_level` — relative pitch shift vs. personal baseline, and
  session-relative loudness level (session P25/P75).
- `prosodic_modulation` — F0 P20–P80 range, and session-relative loudness
  variability (session P25/P75).

Nonverbal (all turn windows):

- `visual_orientation` — visual alignment ratio and dwell against the calibrated
  interaction center (fixed bands).
- `head_gestural_feedback` — nod presence (binary) and session-relative nod rate,
  with interaction context carried through.
- `facial_expressivity` — smile activity (fixed four-band) and session-relative
  smile activation.

## Module map (where each stage lives)

| Stage / concern | Location |
|-----------------|----------|
| Extraction (signal + quality only) | `app/paraverbal/opensmile_extractor.py`, `app/nonverbal/pyfeat_extractor.py` |
| Derivation (raw → processed) | `app/paraverbal/preprocessing.py`, `app/nonverbal/preprocessing.py` |
| Base labels (processed → base labels from `thresholds.yaml`) | `threshold_engine.py` |
| Integrated labels (base labels → one label per family from `label_rules.yaml`) | `label_engine.py` |
| Orchestration (single background pass) | `pipeline.py` |
| Config load / validate / version / hash | `config_loader.py` |
| Personal baseline (derive + read) | `calibration.py` |
| Legacy flat-JSON read compatibility | `legacy_adapter.py` |
| Typed stage contracts (Pydantic, not SQL) | `schemas.py` |
| Methodology configuration | `config/processing.yaml`, `config/thresholds.yaml`, `config/label_rules.yaml` |
| Relabel stored turns without re-extraction | `../scripts/relabel_multimodal.py` |

The extractors are the only code that touches OpenSMILE, Py-Feat, or media. The
threshold and label engines reference only feature names and configuration —
never signal internals.

## Configuration

Methodology lives in YAML (this module's `config/`); infrastructure lives in
`.env`. All three YAML files carry a top-level `version:` string, and every
persisted result records the three versions plus a deterministic `config_hash`
(SHA-256 over the canonical, key-sorted merged config) so any label is traceable
to the exact methodology that produced it.

- **`processing.yaml`** — derivation parameters (e.g. `min_pause_ms`,
  `min_voiced_duration_ms`, `sample_fps`, gaze `alignment_tolerance_radians`,
  smile `au12_active_threshold`, nod detector params).
- **`thresholds.yaml`** — per-feature strategy bands (`fixed_bands`,
  `baseline_delta`, `session_percentiles`, `binary`, `four_band`,
  `passthrough`) with explicit inclusive-boundary semantics, plus
  `min_turns_for_session_stats`.
- **`label_rules.yaml`** — ordered per-family rules (`all` = AND, `any` = OR,
  first match wins, explicit `fallback`, explicit `unavailable`).

### Null methodology values

A value present in YAML but set to `null` is preserved as "undecided". The
config loader distinguishes an absent required structural key (a misconfiguration
that raises `ConfigError` naming the file) from a present-`null` leaf. A
present-`null` methodology value makes the dependent feature
`feature_unavailable`; the pipeline never invents a number to fill it. Several
provisional values (gaze tolerance, AU12 threshold, nod parameters, some band
edges) are `null` today by design.

### Session-relative references

Session-relative families (loudness level/variability, nod rate, smile
activation) use per-interview P25/P75 references computed in a **two-pass**
process over the interview's own turns. If fewer than
`min_turns_for_session_stats` qualifying turns exist, the references are not
computed and every session-relative family yields `insufficient_reference_data`.
Fixed-band families are unaffected by the guard.

## Personal-baseline calibration flow

1. `POST /medical-interviews/calibration/baseline` (authenticated) receives the
   calibration media upload without requiring or creating an interview.
2. The upload is written to a **temporary** server file.
3. `calibration.derive_personal_baseline(...)` runs the OpenSMILE and Py-Feat
   extractors over the media and computes numeric-only metrics:
   `baseline_f0_semitones` (median voiced F0 **in semitones, never Hertz**),
   `baseline_loudness`, `neutral_head_yaw/pitch/roll`, and required
   `neutral_gaze_yaw/pitch`; if either gaze axis is unavailable, the
   complete personal baseline is unavailable rather than partially populated.
4. The result is validated against the `PersonalBaseline` schema and returned
   **numeric-only** to the UI, which holds it in memory.
5. The **temporary media is deleted**; no calibration media is persisted, and no
   new database table is introduced.
6. Only after the user confirms starting the simulation does the UI create the
   interview and save the technical result and complete baseline together in
   `interview_metadata.calibration` before starting it.

Cancelling before confirmation therefore leaves no interview record. The legacy
`POST /medical-interviews/{id}/calibration/baseline` endpoint remains compatible
with existing unstarted interviews and rejects overwrites after start. The
existing `PUT /calibration` device-check behavior is preserved.
`calibration.read_personal_baseline(...)` is the single accessor the pipeline
uses to read the stored baseline.

## Relabeling without re-extraction

`scripts/relabel_multimodal.py` re-derives base and integrated labels for stored
turns using the **current** `thresholds.yaml` / `label_rules.yaml`, reading each
turn's already-persisted `raw`/`processed` blocks. It never re-runs OpenSMILE or
Py-Feat: it reconstructs the typed processed features, recomputes session
references with the same two-pass guard, and rewrites
`base_labels`/`integrated_labels`/`versions`/`config_hash` while preserving
`raw`/`processed`/`quality`/`status`/`reason`.

```bash
python -m scripts.relabel_multimodal <interview_id> [<interview_id> ...]
```

The `backfill_observations.py`, `backfill_pyfeat.py`, and `verify_observations.py`
scripts are adjusted to the layered result shape.

## Persistence and legacy compatibility

Per-turn results are written into the existing `interview_turns.paraverbal`
(paraverbal layer) and `interview_turns.nonverbal_features` (nonverbal layer)
JSON columns — no schema migration. Each layer carries
`raw`/`processed`/`base_labels`/`integrated_labels`/`quality`/`versions`/
`config_hash`/`status`/`reason`. The paraverbal layer is `null` for patient
turns; the nonverbal layer is present for all turns. Unavailable values are
`null` plus a `status` and `reason`, never a fabricated measurement.

`legacy_adapter.py` normalizes pre-refactor flat JSON into the layered read shape
so old rows keep rendering. Legacy families that were never computed are surfaced
as `unavailable` with a reason; only the genuine legacy `temporal_profile` is
surfaced as the `temporal` integrated label.

## Entry point

The interview recordings router schedules the pipeline as a background task
(`background_tasks.add_task(process_multimodal_interview, ...)`); it performs no
inline processing. The pipeline owns its own DB session, updates the
`observation_processing` lifecycle (stages `queued` → `calibration` →
`paraverbal_extraction` → `paraverbal_preprocessing` → `nonverbal_extraction` →
`nonverbal_preprocessing` → `thresholding` → `labeling` → `finished`; statuses
`queued`/`processing`/`complete`/`partial`/`failed`/`unavailable`), and never
propagates exceptions to its caller. A single missing feature yields a `partial`
result rather than failing the whole run.
