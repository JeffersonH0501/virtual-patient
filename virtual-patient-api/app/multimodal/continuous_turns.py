"""Runtime provenance and isolated student-audio feature extraction."""
import hashlib
import json
import sys
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=4)
def _runtime_hash(files):
    digest = hashlib.sha256()
    for name, _, _ in files:
        with Path(name).open('rb') as source:
            digest.update(hashlib.file_digest(source, 'sha256').digest())
    return digest.hexdigest()


def runtime_identity():
    from app.multimodal.extraction_provenance import APP_ROOT, SOURCE_FILES, MODEL_FILES
    paths = [APP_ROOT / name for name in (*SOURCE_FILES, 'multimodal/continuous_turns.py')]
    paths.extend(APP_ROOT / 'nonverbal/models' / name for name in MODEL_FILES)
    return _runtime_hash(tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths))










if __name__ == '__main__':
    # OpenSMILE runs before any visual native imports, in its own short-lived process.
    from app.paraverbal.opensmile_extractor import StudentTurnAudio, analyze_student_turns
    request = json.load(sys.stdin)
    raw = analyze_student_turns(Path(request['path']), [StudentTurnAudio(
        turn_id=request['id'], start_ms=request['start'], end_ms=request['end'], transcript=request['transcript'],
        message_id=request.get('message_id'))])
    result = raw.get(request['id'])
    print(json.dumps(result.model_dump(mode='json') if result else None))
