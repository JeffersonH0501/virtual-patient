"""Validation shared by capture endpoints and historical evidence readers."""

MAX_ROI_SNAPSHOTS = 14_400  # Two hours at the browser's 500 ms sampling interval.


def validate_patient_roi(snapshots, duration_ms=None):
    from fastapi import HTTPException
    try:
        parse_patient_roi_snapshots(snapshots, duration_ms)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

ROI_FIELDS = {
    "timestamp_ms": "timestampMs",
    "x_normalized": "xNormalized",
    "y_normalized": "yNormalized",
    "width_normalized": "widthNormalized",
    "height_normalized": "heightNormalized",
}


def parse_patient_roi_snapshots(snapshots, duration_ms=None):
    """Return canonical fields for analysis, leaving the stored payload intact."""
    if not isinstance(snapshots, list) or len(snapshots) > MAX_ROI_SNAPSHOTS:
        raise ValueError("Invalid patient ROI timeline")

    canonical = []
    previous = 0
    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or len(snapshot) != len(ROI_FIELDS):
            raise ValueError("Invalid patient ROI sample")
        values = {field: snapshot.get(alias, snapshot.get(field)) for field, alias in ROI_FIELDS.items()}
        if any(
            type(value) not in (int, float)
            or not float("-inf") < value < float("inf")
            for value in values.values()
        ):
            raise ValueError("Patient ROI samples require finite numeric fields")
        timestamp = values["timestamp_ms"]
        if timestamp < previous or (duration_ms is not None and timestamp > duration_ms):
            raise ValueError("Patient ROI timestamp is outside the capture timeline")
        x, y = values["x_normalized"], values["y_normalized"]
        width, height = values["width_normalized"], values["height_normalized"]
        if not (0 < width <= 1 and 0 < height <= 1 and -width < x < 1 and -height < y < 1):
            raise ValueError("Patient ROI must intersect the viewport")
        previous = timestamp
        canonical.append(values)
    return canonical


def slice_patient_roi_snapshots(snapshots, start_ms, duration_ms):
    """Keep the region active at clip start, followed by clip-local changes."""
    try:
        canonical = parse_patient_roi_snapshots(snapshots)
    except ValueError:
        return None
    preceding = [item for item in canonical if item["timestamp_ms"] <= start_ms]
    selected = preceding[-1:] + [item for item in canonical
        if start_ms < item["timestamp_ms"] <= start_ms + duration_ms]
    return [{**item, "timestamp_ms": max(0, item["timestamp_ms"] - start_ms)} for item in selected]
