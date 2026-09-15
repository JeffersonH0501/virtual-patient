"""Multimodal pipeline module.

Coordinates the staged, versioned multimodal pipeline: calibration,
extraction, preprocessing, thresholding, base labels, and integrated labels.
Typed stage contracts live in ``schemas.py`` and are data models only, never
SQL tables.
"""
