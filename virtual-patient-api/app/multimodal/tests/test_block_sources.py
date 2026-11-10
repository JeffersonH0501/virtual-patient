"""Encoded local windows use one preserved audiovisual original."""
import hashlib
import subprocess
from types import SimpleNamespace
from app.media.probe import probe_media_timing
from app.multimodal.block_turns import prepare_block_sources, source_identity


def test_analysis_excludes_technical_wait_and_keeps_the_original_unchanged(tmp_path):
    path = tmp_path / 'original.webm'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=64x64:r=10:d=3',
        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', '-c:v', 'libvpx', '-c:a', 'libopus', '-threads', '1', str(path)], check=True, timeout=20)
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    segment = SimpleNamespace(calibration={})
    block = SimpleNamespace(id='synthetic', sha256=digest, metadata_hash='metadata', storage_key='original.webm')
    window = {'start_ms': 250, 'end_ms': 750}
    source = {'window': window, 'identity': source_identity(block, segment, window)}
    storage = SimpleNamespace(resolve=lambda key: tmp_path / key)
    turn = SimpleNamespace(id='synthetic-turn', message_id=1, speaker='student', transcript='Synthetic speech')
    output, audio, offset, duration, origin = prepare_block_sources(storage, block, segment, turn, source, tmp_path)
    assert audio['turn_duration_ms'] == 500
    assert audio['transcript_ref']['message_id'] == 1
    assert offset == 250 and origin == 0 and duration == 1750
    assert probe_media_timing(output)['duration_ms'] <= 1800
    assert path.read_bytes() == content
