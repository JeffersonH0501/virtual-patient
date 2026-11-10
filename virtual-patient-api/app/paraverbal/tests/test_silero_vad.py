import pytest

from app.paraverbal.silero_vad import speech_intervals


def test_intervals_merge_short_gaps_and_exclude_edge_silence():
    probabilities = [0.1, 0.8, 0.8, 0.1, 0.1, 0.1, 0.9, 0.1, 0.1, 0.1, 0.1, 0.8, 0.1]
    assert speech_intervals(probabilities, duration_ms=416) == [(32, 224), (352, 384)]


def test_intervals_clamp_last_frame_and_do_not_invent_speech():
    assert speech_intervals([0.0, 0.7], duration_ms=45) == [(32, 45)]
    assert speech_intervals([0.1, 0.2], duration_ms=64) == []


def test_nonfinite_probabilities_are_rejected():
    with pytest.raises(ValueError):
        speech_intervals([float('nan')], duration_ms=32)


def test_vad_metrics_exclude_edge_silence_and_short_internal_gaps():
    from app.multimodal.schemas import ParaverbalRawFeatures
    from app.paraverbal.preprocessing import preprocess_paraverbal
    raw = ParaverbalRawFeatures(word_count=12, voiced_duration_ms=2000,
        f0_samples_semitones=[5, 6], loudness_samples=[.2, .3],
        pause_segments_ms=[100, 600], turn_duration_ms=4000,
        vad_speech_intervals_ms=[(500, 1500), (1600, 2100), (2700, 3200)],
        extractor={}, audio_quality={})
    result = preprocess_paraverbal(raw)
    assert result.speech_rate_wpm == pytest.approx(266.667)
    assert result.articulation_rate_wpm == 360
    assert result.pause_count == 1
    assert result.total_pause_duration_ms == 600
    assert result.pause_time_ratio == pytest.approx(.222)


def test_missing_vad_does_not_reuse_f0_silence_as_speech():
    from app.multimodal.schemas import ParaverbalRawFeatures
    from app.paraverbal.preprocessing import preprocess_paraverbal
    raw = ParaverbalRawFeatures(word_count=3, voiced_duration_ms=1000,
        f0_samples_semitones=[5, 6], loudness_samples=[.2, .3], pause_segments_ms=[800],
        turn_duration_ms=2000, extractor={}, audio_quality={})
    result = preprocess_paraverbal(raw)
    assert result.speech_rate_wpm is None and result.pause_count is None


def test_vad_survives_acoustic_extractor_failure(tmp_path, monkeypatch):
    import wave
    from app.paraverbal import silero_vad
    from app.paraverbal.opensmile_extractor import _extract_raw_features

    path = tmp_path / 'audio.wav'
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(bytes(32000))
    monkeypatch.setattr(silero_vad, 'detect_speech', lambda samples: ([(100, 900)], [.8]))

    class BrokenSmile:
        def process_file(self, path):
            raise ValueError('synthetic extraction failure')

    raw = _extract_raw_features(path, [0.] * 16000, 1000, 'two words', smile=BrokenSmile(), min_voiced_duration_ms=300)
    assert raw.vad_speech_intervals_ms == [(100, 900)]
    assert raw.f0_samples_semitones == [] and raw.loudness_samples == []
    assert {'f0_unavailable', 'loudness_unavailable'} <= set(raw.audio_quality['issues'])


def test_extracts_acoustic_samples_only_inside_vad_intervals(tmp_path, monkeypatch):
    import wave
    import pandas as pd
    from app.paraverbal import silero_vad
    from app.paraverbal.opensmile_extractor import _extract_raw_features
    path = tmp_path / 'audio.wav'
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b'\x00\x00' * 16000)
    index = pd.MultiIndex.from_tuples([(pd.Timedelta(milliseconds=t), pd.Timedelta(milliseconds=t + 20))
                                      for t in (0, 100, 200, 300)], names=['start', 'end'])
    frame = pd.DataFrame({'F0semitoneFrom27.5Hz': [10., 20., 30., 40.],
                          'loudness': [.1, .2, .3, .4]}, index=index)
    monkeypatch.setattr(silero_vad, 'detect_speech', lambda samples: ([(100, 250)], [.1, .9]))
    smile = type('Extractor', (), {'process_file': lambda self, path: frame})()
    raw = _extract_raw_features(path, [0.] * 16000, 1000, 'two words', smile=smile,
                                min_voiced_duration_ms=300, turn_start_ms=5000)
    assert raw.f0_samples_semitones == [20., 30.]
    assert raw.loudness_timestamps_ms == [5110., 5210.]
    assert raw.vad_speech_intervals_ms == [(100, 250)]
    assert raw.audio_quality['vad_speech_duration_ms'] == 150
