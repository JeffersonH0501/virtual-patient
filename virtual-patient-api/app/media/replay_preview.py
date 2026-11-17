"""One continuous, lightweight replay of the interview built from its per-turn originals.

The originals stay untouched for analysis. The preview lays each clip on the interview clock,
fills gaps with black and silence, mixes the patient voice at its recorded playback offset and
encodes 480p at 15 fps so review plays as a single ordinary video.
"""
import logging
import subprocess
import time
from pathlib import Path

from app.speech.preserved_audio import patient_audio_key

logger = logging.getLogger(__name__)

PREVIEW_VERSION = "replay_preview_480p15_v1"
WIDTH, HEIGHT, FPS = 854, 480, 15
# Same +6 dB as the live interview (utils/patientVoice.ts); the final limiter prevents clipping.
PATIENT_VOICE_GAIN = 2.0
ENCODE_THREADS = 2


def preview_key(interview_id, recording_id) -> str:
    return f"interviews/{interview_id}/{recording_id}/replay/preview.mp4"


def _seconds(ms: float) -> str:
    return f"{max(0.0, ms) / 1000:.3f}"


def build_preview_command(clips, voices, total_ms, output: Path) -> list[str]:
    """ffmpeg arguments for ``clips`` [(path, start_ms, duration_ms, has_audio)] and ``voices`` [(path, at_ms, length_ms)]."""
    inputs, video, audio = [], [], []
    cursor = 0.0
    for index, (path, start, duration, has_audio) in enumerate(clips):
        inputs += ["-i", str(path)]
        if start > cursor:
            video.append(f"color=black:s={WIDTH}x{HEIGHT}:r={FPS}:d={_seconds(start - cursor)},format=yuv420p,setsar=1")
            cursor = start
        following = clips[index + 1][1] if index + 1 < len(clips) else total_ms
        length = min(start + duration, following, total_ms) - cursor
        if length <= 0:
            continue
        offset = cursor - start
        # Scale/pad each clip but do not resample its frame clock here; the whole concatenated
        # stream is put on one continuous 15fps grid after concat, so turn cuts carry no black
        # frame and the video plays as one continuous recording.
        video.append(f"[{index}:v:0]trim=start={_seconds(offset)}:duration={_seconds(length)},setpts=PTS-STARTPTS,"
                     f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                     f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")
        if has_audio:
            delay = int(round(cursor))
            audio.append(f"[{index}:a:0]atrim=start={_seconds(offset)}:duration={_seconds(length)},asetpts=PTS-STARTPTS,"
                         f"aformat=sample_rates=48000:channel_layouts=mono,adelay={delay}:all=1")
        cursor += length
    if cursor < total_ms:
        video.append(f"color=black:s={WIDTH}x{HEIGHT}:d={_seconds(total_ms - cursor)},format=yuv420p,setsar=1")
    for path, at, length in voices:
        index = len(inputs) // 2
        inputs += ["-i", str(path)]
        audio.append(f"[{index}:a:0]atrim=duration={_seconds(length)},asetpts=PTS-STARTPTS,"
                     f"aformat=sample_rates=48000:channel_layouts=mono,volume={PATIENT_VOICE_GAIN},adelay={int(round(at))}:all=1")
    graph = [f"{chain}[v{n}]" for n, chain in enumerate(video)]
    # Resample the joined stream to one continuous 15fps grid so boundaries carry no black frame.
    graph.append("".join(f"[v{n}]" for n in range(len(video))) +
                 f"concat=n={len(video)}:v=1:a=0,fps={FPS}[video]")
    graph.append(f"anullsrc=r=48000:cl=mono,atrim=duration={_seconds(total_ms)}[silence]")
    graph += [f"{chain}[a{n}]" for n, chain in enumerate(audio)]
    graph.append("[silence]" + "".join(f"[a{n}]" for n in range(len(audio))) +
                 f"amix=inputs={len(audio) + 1}:normalize=0:duration=first,alimiter=limit=0.89:level=false[audio]")
    return ["ffmpeg", "-v", "error", "-y", "-nostats", "-progress", "pipe:1", *inputs,
            "-filter_complex", ";".join(graph), "-map", "[video]", "-map", "[audio]",
            # A keyframe each second keeps playback smooth and seeks landing cleanly across cuts.
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-g", str(FPS), "-keyint_min", str(FPS),
            "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-threads", str(ENCODE_THREADS),
            "-movflags", "+faststart", "-t", _seconds(total_ms), str(output)]


def encode_preview(command, total_ms, report) -> None:
    """Run ffmpeg, calling ``report(percent)`` as it advances."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    last = -1
    try:
        for line in process.stdout:
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and value.isdigit() and total_ms:
                percent = min(99, int(int(value) / 1000 / total_ms * 100))
                if percent > last:
                    last = percent
                    report(percent)
        error = process.stderr.read()
        if process.wait(timeout=600) != 0:
            raise RuntimeError(f"Replay preview encoding failed: {error.strip()[-500:]}")
    finally:
        if process.poll() is None:
            process.kill()


def _resolve_patient_voice(interview_id: int, recording_id: str, message_id: int):
    """Preserved TTS for a reply, regenerating it when the live playback never saved it.

    The opening greeting plays before the recording segment exists, so its exact TTS was never
    preserved. Deterministic synthesis from the stored text and personality reproduces it.
    """
    from app.core.database import SessionLocal
    from app.media import get_media_storage
    from app.models.medical_interview import InterviewMessageDB, MedicalInterviewDB
    from app.speech.preserved_audio import preserved_patient_audio
    from app.speech.service import SpeechService

    storage = get_media_storage()
    try:
        return storage.resolve(patient_audio_key(interview_id, recording_id, message_id))
    except FileNotFoundError:
        pass
    with SessionLocal() as db:
        message = db.get(InterviewMessageDB, message_id)
        interview = db.get(MedicalInterviewDB, interview_id)
        if message is None or interview is None or not message.content:
            return None
        text = message.content
        personality = interview.personality.namespace_key if interview.personality else None
        gender = interview.patient_gender
    try:
        return preserved_patient_audio(storage, interview_id, recording_id, message_id,
            lambda: SpeechService().synthesize_patient_message(text, personality, gender))
    except (OSError, ValueError) as error:
        logger.warning("replay_preview could not restore patient audio interview_id=%s message_id=%s: %s",
                       interview_id, message_id, error)
        return None


def build_replay_preview(interview_id: int, recording_id: str) -> None:
    """Build the preview for a finalized recording and record its progress on the recording."""
    from app.core.database import SessionLocal
    from app.media import get_media_storage
    from app.media.probe import has_audio_stream
    from app.models.medical_interview import InterviewRecordingDB
    from app.multimodal.turn_staging import ordered_turn_media

    storage = get_media_storage()

    def update(**state):
        with SessionLocal() as db:
            recording = db.get(InterviewRecordingDB, recording_id, with_for_update=True)
            if recording is None:
                return
            capture = dict(recording.capture_config or {})
            capture["replay_preview"] = {**capture.get("replay_preview", {}), **state}
            recording.capture_config = capture
            db.commit()

    with SessionLocal() as db:
        media = [item for item in ordered_turn_media(db, recording_id) if item.duration_ms]
        media.sort(key=lambda item: item.session_clock_ms)
        rows = [(item.storage_key, item.session_clock_ms, item.duration_ms, item.speaker, item.message_id,
                 dict(item.turn_metadata or {})) for item in media]
    clips, voices = [], []
    for storage_key, start, duration, speaker, message_id, metadata in rows:
        try:
            path = storage.resolve(storage_key)
        except FileNotFoundError:
            continue
        clips.append((path, start, duration, speaker == "student" and has_audio_stream(path)))
        begin, end = metadata.get("playback_start_ms"), metadata.get("playback_end_ms")
        if speaker == "patient" and message_id is not None and begin is not None and end is not None and end > begin:
            voice = _resolve_patient_voice(interview_id, recording_id, message_id)
            if voice is not None:
                voices.append((voice, start + begin, end - begin))
    total_ms = max((start + duration for _, start, duration, _ in clips), default=0)
    if not clips or total_ms <= 0:
        update(status="unavailable", progress=0)
        return
    target = (storage.root / preview_key(interview_id, recording_id)).resolve()
    storage._assert_within_root(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.stem}.tmp.mp4")
    update(status="processing", progress=0)
    started = time.perf_counter()
    try:
        encode_preview(build_preview_command(clips, voices, total_ms, temporary), total_ms,
                       lambda percent: update(progress=percent))
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    update(status="ready", progress=100, version=PREVIEW_VERSION, duration_ms=total_ms)
    logger.info("replay_preview interview_id=%s recording_id=%s clips=%s duration_ms=%s encode_ms=%.0f",
                interview_id, recording_id, len(clips), total_ms, (time.perf_counter() - started) * 1000)
