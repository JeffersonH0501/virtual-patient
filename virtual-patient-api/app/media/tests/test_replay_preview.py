"""The continuous replay preview keeps every clip on the interview clock."""
import json
import subprocess

from app.media.replay_preview import build_preview_command, encode_preview


def _clip(path, seconds, audio):
    sources = ["-f", "lavfi", "-i", f"color=c=gray:s=320x180:r=30:d={seconds}"]
    if audio:
        sources += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *sources, "-c:v", "libvpx", *(["-c:a", "libopus"] if audio else []),
                    "-threads", "1", str(path)], check=True, timeout=30)
    return path


def test_preview_spans_the_timeline_with_gaps_overlaps_and_the_patient_voice(tmp_path):
    student = _clip(tmp_path / "student.webm", 2, True)
    camera = _clip(tmp_path / "camera.webm", 3, False)
    voice = tmp_path / "voice.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=1",
                    "-c:a", "libmp3lame", str(voice)], check=True, timeout=30)
    # The camera clip overlaps the student clip by 100 ms and is followed by a 500 ms gap.
    clips = [(student, 0, 2000, True), (camera, 1900, 3000, False)]
    output = tmp_path / "preview.mp4"
    reported = []
    encode_preview(build_preview_command(clips, [(voice, 2500, 1000)], 5400, output), 5400, reported.append)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height,avg_frame_rate",
                                       "-of", "json", str(output)], check=True, capture_output=True, text=True).stdout)
    streams = {stream["codec_name"]: stream for stream in probe["streams"]}
    assert abs(float(probe["format"]["duration"]) - 5.4) < 0.2
    assert (streams["h264"]["height"], streams["h264"]["avg_frame_rate"]) == (480, "15/1")
    assert "aac" in streams
    assert reported == sorted(reported) and all(0 <= value < 100 for value in reported)


def test_command_trims_overlaps_and_fills_gaps_with_black():
    command = build_preview_command([("a", 0, 2000, True), ("b", 1900, 1000, False), ("c", 3500, 500, False)], [], 4000, "out.mp4")
    graph = command[command.index("-filter_complex") + 1]
    assert "[0:v:0]trim=start=0.000:duration=1.900" in graph
    assert "color=black:s=854x480:r=15:d=0.600" in graph
    assert "adelay=0:all=1" in graph and "concat=n=4" in graph


def test_missing_greeting_audio_is_regenerated_from_the_stored_message(tmp_path, monkeypatch):
    """The opening greeting's TTS, never preserved live, is restored for the replay preview."""
    from types import SimpleNamespace
    from app.media import replay_preview

    storage = SimpleNamespace(root=tmp_path)
    monkeypatch.setattr(replay_preview, "get_media_storage", lambda: storage, raising=False)
    import app.media
    monkeypatch.setattr(app.media, "get_media_storage", lambda: storage)

    class _MissingStorage:
        def resolve(self, key):
            raise FileNotFoundError(key)
    monkeypatch.setattr("app.media.get_media_storage", lambda: _MissingStorage())

    message = SimpleNamespace(content="Hola, mucho gusto.")
    interview = SimpleNamespace(personality=SimpleNamespace(namespace_key="rude_unfriendly"), patient_gender="female")

    class _Session:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def get(self, model, identifier):
            return message if model.__name__ == "InterviewMessageDB" else interview
    monkeypatch.setattr("app.core.database.SessionLocal", _Session)

    captured = {}

    def fake_preserve(storage_arg, interview_id, recording_id, message_id, generate):
        captured["args"] = (interview_id, recording_id, message_id)
        captured["audio"] = generate()
        return tmp_path / "restored.mp3"

    monkeypatch.setattr("app.speech.preserved_audio.preserved_patient_audio", fake_preserve)
    monkeypatch.setattr("app.speech.service.SpeechService.synthesize_patient_message",
                        lambda self, text, personality, gender: SimpleNamespace(text=text, personality=personality, gender=gender))

    result = replay_preview._resolve_patient_voice(7, "rec-1", 98)
    assert result == tmp_path / "restored.mp3"
    assert captured["args"] == (7, "rec-1", 98)
    assert captured["audio"].text == "Hola, mucho gusto." and captured["audio"].gender == "female"
