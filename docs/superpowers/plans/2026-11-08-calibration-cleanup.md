# Calibration reference cleanup

Only started interviews retain calibration references. Preparation captures and
profiles remain temporary for retries. Confirmed exit erases only calibration
videos/results, preserving the interview record and unrelated content.

1. Add owner-only discard guarded by the interview row lock and start time.
   Commit a server-owned invalidation marker and delete capture rows/profile
   before erasing only the private calibration directory. Retry physical failures.
2. Record server-owned activity on upload/profile save. Every five minutes,
   clear calibration after one inactive hour and reconcile orphan calibration
   files after five minutes, rechecking references under the publication lock.
3. Await discard on confirmed exit, attempt it on navigation/page hide, skip it
   after successful start, and handle late creation/analysis and expired preparation.
4. Test permissions, started-reference preservation, disk failures, late results,
   orphan files and UI retries in Docker. Update the contract/manuscript and clean
   existing abandoned calibration data without deleting interview records.
