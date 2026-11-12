# Recap (interview player) — audit, fixes and validation

Scope: the review-mode playback of a finished clinical interview — frontend
(`useBlockPlayback`, `BlockInterviewRecap`, `InterviewRecap`), backend recap
assembly (`/recap`, `list_blocks`, `block_turns`), media serving and the
evaluation-detail integration. No science, media, timestamps or live-simulation
behavior were changed.

## 1. How it works (verified)

- UI mount: `ClinicalChat` (review) → `InterviewRecap` (fetch + 3s processing
  poll) → `BlockInterviewRecap` → `useBlockPlayback`.
- Data: `GET /medical-interviews/{id}/recap` → `InterviewRecapResponse`
  (`recording_status`, `duration_ms`, `blocks[]`, `turns[]`,
  `observation/evaluation_processing`). Blocks come from `list_blocks`
  (`recording_blocks.py`), ordered by `segment.sequence, block.order`, each with
  an accumulated `offset_ms` and confirmed `duration_ms`.
- Timeline source of truth: a single `time` clock (seconds) in `useBlockPlayback`
  slaved to the active `HTMLMediaElement.currentTime` via one
  `requestAnimationFrame` loop — no artificial timers, no competing clocks. Total
  `duration` and per-block windows come from the server manifest; the client
  never invents durations.
- Media: student video is the `<video src>` (HTTP Range, `crossOrigin`); patient
  audio is fetched as a blob and cached as an object URL (current + next block
  only, older ones revoked; all revoked on unmount). Seeking captures a poster
  frame to avoid a black flash.
- Backend never fabricates timing: `block_turns.stage_block_turns` collapses an
  unreliable block to `start=end=0` + `timing_quality='unavailable'`, which
  `_turn_response` exposes as `null` timestamps. Missing clips degrade in
  `list_blocks` to `null` sources; a per-turn missing modality stays `null`.

The architecture is sound (single clock, server-authoritative timeline, graceful
partial rendering, resource cleanup). It needed targeted fixes, not a rewrite.

## 2. Problems found (root cause + evidence)

1. **A bad patient-audio clip could wedge its block (functional, P0).** When a
   patient-audio blob failed to load/decode, `block.patientAudioSource` stayed
   truthy, so the sync effects kept waiting on a dead `<audio>` element and the
   player stalled or errored for that block instead of playing the student video
   of the same block. Evidence: `useBlockPlayback` gated video/audio sync on
   `block.patientAudioSource` (truthy even when the element errored).
2. **`list_blocks` could 500 the whole recap on a malformed block (robustness,
   P1).** `block.block_metadata["patient_message_id"]` was dereferenced
   unconditionally (`recording_blocks.py`), so an externally-mutated row missing
   that key would raise `KeyError` → 500 for the entire recap.
3. **Unbounded processing poll (UX, P2).** `InterviewRecap` re-polled every 3s
   with no maximum while `observation/evaluation_processing` was
   `queued|processing`, so a stuck status polled forever.

(No desync/seek/ordering defects were found: the single-clock design, drift
dead-band and `readyState/seeking` guards already handle seeking, buffering and
turn selection correctly, as the existing test suite asserts.)

## 3. Fixes implemented (localized)

- `useBlockPlayback.ts`:
  - Added `failedAudio` tracking + `patientAudioUsable` derived flag. The
    video/audio sync effects and the "nothing playable" guard now use
    `patientAudioUsable` instead of the raw `patientAudioSource`, so a block with
    student video keeps playing (patient segment muted) when its patient audio
    fails, and the video no longer waits on a dead audio element.
  - The patient `<audio> onError` now marks that one source failed (and clears
    its buffering flag) instead of erroring the whole recap. A failed *preload
    fetch* is treated as a lost optimization only (the element can still load the
    source directly) — it does not poison the source.
  - A genuinely media-less block (no video and no usable patient audio) still
    surfaces a recoverable error (time preserved, play button available) rather
    than inventing playback time — preserving the existing contract.
- `recording_blocks.py` `list_blocks`: read `patient_message_id` defensively
  (`(block.block_metadata or {}).get(...)`); a block without it degrades to
  `patient_audio_source = None` instead of 500-ing the recap.
- `InterviewRecap.tsx`: bounded the processing poll to `MAX_POLLS = 400`
  (~20 min at 3s); after that the loader stops and the user can retry.

## 4. Tests executed

- New UI test (`BlockInterviewRecap.test.tsx`): "keeps playing the student video
  when the patient audio clip fails to load" — asserts no `alert`, play button →
  pause, `play()` called, video not paused. **Passes.**
- Existing player suite `BlockInterviewRecap.test.tsx`: **21/21 pass** (20
  pre-existing + the new one), covering seeking at the current position, next-
  video preload + boundary reuse, recoverable error on a media-less block,
  next-video preload failure + retry, truncated-vs-complete final frame,
  buffering freeze, audio alignment after seek, preload/eviction + unmount
  revoke, stale-play rejection handling, interview-identity reset, and
  mute/offset correctness.
- Full `src/components/ClinicalChat` UI suite: **113/113 pass**; `yarn lint`
  clean; `yarn build` (typecheck) succeeds.
- Backend recap/blocks: `test_recording_blocks.py` + `test_interview_recordings.py`
  + `test_canonical_recording_contract.py` → **33/33 pass** (route existence,
  Range 200/206/416, `_without_none`/`_turn_response` canonical contract,
  duration fallback, partial media, stale-capture fencing, one-preserved-original
  replay).

## 5. Residual risks and pending manual verification

- Automated media tests run in jsdom with mocked `HTMLMediaElement`; they verify
  logic and state transitions, not real audio/video decoding. The following need
  manual verification in a real browser with real media:
  - End-to-end playback of a full real interview (short and long), scrubbing,
    forward/back jumps, turn selection, student↔patient transitions.
  - A real corrupt/short clip mid-interview (confirm the rest still plays).
  - Slow/interrupted network for block media and patient audio.
  - Cross-browser (Chrome/Firefox/Safari) autoplay-policy and Range behavior.
  - Page reload / navigation away mid-playback (no background audio, URLs freed).
- Not changed and still true: durations are never invented; a single missing clip
  degrades (manifest `null` source / recoverable UI error) rather than failing
  the whole recap; evaluation-detail opening is pure display and does not reload
  or reset playback.
- The bounded recap poll (400) is a safety cap, not a fix for a stuck pipeline;
  if processing legitimately takes >20 min the user must retry.
