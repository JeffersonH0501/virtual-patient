"""Dev/debug-only multimodal calibration helpers.

This package exposes pure, in-memory debug extraction for the calibration debug
tool. It never persists media, never writes to the database, and never derives
processed features, base labels, integrated labels, or turn aggregates. It emits
raw frame-level values only, so the frontend calibration tool can show a live,
per-frame readout of what the extractors observe.

Everything here is intended for development use behind authentication and must
not participate in the production interview/calibration persistence flow.
"""
