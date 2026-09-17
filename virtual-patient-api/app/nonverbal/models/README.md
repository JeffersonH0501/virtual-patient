# Nonverbal model artifacts

`blazegaze_mpiifacegaze.keras` is the unmodified BlazeGaze artifact from
WebEyeTrack commit `75fbd2f5f784f2eb3a39675a8dcbf1b01c697f1c`.

The Python package is installed from that exact commit. The backend adapter calls
`WebEyeTrack.step` with the shared MediaPipe result; `process_frame` is not used.
The Docker build applies only Python 3.12 dataclass-default compatibility fixes;
the preprocessing and inference algorithms remain unchanged.

- Upstream: https://github.com/RedForestAI/WebEyeTrack
- License: MIT
- Artifact: `python/webeyetrack/model_weights/blazegaze_mpiifacegaze.keras`
- SHA-256: `5b011cfe82466896e27b1ac3e18130117cafbc02dbc964a1ad7315f62005cc05`
- Serialization metadata: Keras 3.10.0

The artifact must not be regenerated or converted implicitly. The API verifies
its digest before loading it.

`face_landmarker_v2_with_blendshapes.task` is the unmodified MediaPipe model
distributed in the same pinned WebEyeTrack commit. Its SHA-256 is
`64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`.

## CCDb-HG Wave 3 input

`ccdbhg_cnn_lmk_hp/ckpt.pth.tar` is the unmodified `cnn_lmk_hp` checkpoint from
CCDb-HG commit `e67ea201db01ce24a9eb546305752de7ebfe69fd`.

- Upstream: https://github.com/idiap/ccdbhg-head-gesture-recognition
- Upstream path: `src/model_checkpoints/cnn_lmk_hp/cnn/ckpt.pth.tar`
- SHA-256: `7f390f20fe02e1636cc18b7d120ab7f60c99e5c972b5953e6d064c47b495c556`
- `config.yaml` SHA-256: `50a53c77fb8fdac072bbbc13c876fa7694f3e6dfdf8a03b0f98d8570092bca0b`
- `train_stats.pkl` SHA-256: `4495249e3f88f867c3f2f39e00027202abebc10926187f22c3e3efe5a718608e`
- License recorded upstream: GPL-3.0-only (copy stored beside the checkpoint)

No upstream GPL source code is vendored. The project adapter will independently
implement the tensor contract over the existing shared MediaPipe observations.
The exact channel order is `head_yaw`, `head_roll`, `head_pitch`, followed by
`x`, `y`, `z` for `left_eye`, `right_eye`, `nose`, `ear_l`, and `ear_r`.
