# Interview media

## Capture and recovery

New interviews use `per_turn_v1`. [InterviewCapture](../virtual-patient-ui/src/recording/InterviewCapture.ts) owns one open original once recording begins. Student originals contain camera and microphone and include the silence before the utterance. Patient originals contain the student's camera during the wait and reply. Idle originals have no message and are playable. The greeting starts the recorded clock when playback begins and is excluded from analysis.

The client retains originals locally until an accepted receipt. Segment start and upload retries reuse the original identity. A dropped connection within the same page pauses the recorder and replays the start request to verify ownership. Reload or takeover uses resume, which seals the previous segment and requires a new preparation. Device or geometry changes also require recovery. A stale segment cannot restart itself. Interactive message delivery has a 120-second total deadline. Explicit retry reuses the same request and original.

Finalization seals a manifest of accepted and missing originals. Transient upload and finalize failures can be retried. Rejected or unverifiable media becomes unavailable evidence, while conversation text is retained. Stored files use a lossless container rewrite when packet integrity checks pass. `upload_sha256` identifies the uploaded bytes and `sha256` identifies the stored file.

## Replay and analysis

A durable `replay_preview` job builds the private MP4 preview on the interview clock. It joins originals, represents gaps as black and silence, and mixes saved TTS at its playback offset. Review uses the preview and the synchronized transcript. The original media remains the analysis input. Authorizations, deletion and retention apply to both originals and preview.

Student analysis uses the detected speech onset with a 300 ms operational pre-roll. Patient turns contribute visual observations of listening only within confirmed TTS playback. Idle, greeting and unverifiable windows supply no evidence. The paraverbal path uses OpenSMILE/eGeMAPSv02 and speech timing. The visual path uses MediaPipe Face Landmarker for gaze and smile observations and CCDb-HG for head gestures. The pipeline retains measurement, quality and descriptive label layers separately. See [assessment and access](assessment-and-access.md) for which evidence enters prompts.

## Calibration

The official gaze workflow uses five three-second targets followed by a five-second camera reference. The browser records geometry, and the server validates signed checkpoints and the independently fitted MediaPipe profile. The quality policy `mediapipe_five_point_quality_v3` uses geometric eye openness of 0.10 and median/P90 leave-one-target-out normalized error ceilings of 0.35/0.50. The [calibration implementation](../virtual-patient-api/app/nonverbal/mediapipe_calibration.py) defines the full support, coverage and camera-reference gates.

The first quality failure requires a retry. From the second distinct retained quality failure in the same preparation, the server can authorize continuing without gaze if ownership, lifecycle and geometry checks pass. Duplicate uploads and processing errors do not count. This path saves the attempted capture IDs and no fitted gaze profile. The independent audio, smile and nod quality rules still apply. Experimental checks for administrators do not authorize participant capture.

Physical-device timing, gaze agreement, device transferability and independent annotation agreement require separate validation. Operational quality cutoffs describe processing and availability. Gaze, smile and head movements are observations of behavior and do not establish psychological states.

## Nonverbal model artifacts

`face_landmarker_v2_with_blendshapes.task` is the unmodified MediaPipe model
distributed in the pinned source artifact. Its SHA-256 is
`64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`.

### CCDb-HG Wave 3 input

`ccdbhg_cnn_lmk_hp/ckpt.pth.tar` is the unmodified `cnn_lmk_hp` checkpoint from
CCDb-HG commit `e67ea201db01ce24a9eb546305752de7ebfe69fd`.

- Upstream: https://github.com/idiap/ccdbhg-head-gesture-recognition
- Upstream path: `src/model_checkpoints/cnn_lmk_hp/cnn/ckpt.pth.tar`
- SHA-256: `7f390f20fe02e1636cc18b7d120ab7f60c99e5c972b5953e6d064c47b495c556`
- `config.yaml` SHA-256: `50a53c77fb8fdac072bbbc13c876fa7694f3e6dfdf8a03b0f98d8570092bca0b`
- `train_stats.pkl` SHA-256: `4495249e3f88f867c3f2f39e00027202abebc10926187f22c3e3efe5a718608e`
- License recorded upstream: GPL-3.0-only (copy stored beside the checkpoint)

The [local adapter](../virtual-patient-api/app/nonverbal/ccdbhg.py) builds the tensor
from shared MediaPipe observations. The repository carries the checkpoint and its license.
The exact channel order is `head_yaw`, `head_roll`, `head_pitch`, followed by
`x`, `y`, `z` for `left_eye`, `right_eye`, `nose`, `ear_l`, and `ear_r`.

## Face integration fixture

`app/nonverbal/tests/fixtures/face.jpg` is OpenCV's public `samples/data/lena.jpg` fixture, downloaded from
the OpenCV `4.x` branch solely for deterministic backend integration testing.
It is not participant data and must not be used for accuracy claims.

Source: https://github.com/opencv/opencv/blob/4.x/samples/data/lena.jpg
OpenCV license: Apache-2.0.
