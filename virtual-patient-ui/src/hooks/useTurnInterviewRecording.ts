import {useCallback, useEffect, useRef, useState} from 'react';
import {InterviewTurnRecorder} from '../recording/InterviewTurnRecorder';
import {InterviewTurnStore, type TurnCaptureMetadata, type LocalInterviewTurn} from '../recording/InterviewTurnStore';
import {turnJson, turnScope, turnUploadQueue, getTurnManifest, forgetTurnQueue, subscribeTurnConnection} from '../services/recordings/turns';
import type {UseInterviewRecordingOptions} from './useInterviewRecording';
import type {RecordingStatus, SpeechTiming, StudentCaptureTiming} from '../types/recording';

/**
 * Per-turn capture: one recorder spans a single student turn. The patient turn
 * is text-to-speech and carries no captured media, so its lifecycle callbacks
 * do not record. Each student turn uploads its own immutable media file.
 */
export const useTurnInterviewRecording = (options: UseInterviewRecordingOptions) => {
  const [status, setStatus] = useState<RecordingStatus>('idle');
  const [syncPending, setPending] = useState(false);
  const [errorCode, setError] = useState<string | null>(null);
  const [captureId, setCaptureId] = useState<string | null>(null);
  const runtime = useRef<InterviewTurnRecorder | null>(null);
  const writer = useRef<string | null>(null);
  const started = useRef(false);
  const disposed = useRef(false);
  const serial = useRef<Promise<unknown>>(Promise.resolve());
  const completedMs = useRef(options.initialOffsetMs ?? 0);
  const order = useRef(0);
  const latest = useRef(options);
  latest.current = options;
  const sealed = useRef(false);
  const geometry = useRef<string | null>(null);
  const devices = useRef<{camera?: string; microphone?: string} | null>(null);
  const blocked = useRef<string | null>(null);
  const networkPaused = useRef(!navigator.onLine);
  const startRequest = useRef<string | null>(null);
  const startBody = useRef<string | null>(null);
  const starting = useRef(false);
  const startAbort = useRef<AbortController | null>(null);
  const roi = useRef<Record<string, number>[]>([]);
  const closingTurn = useRef(false);
  const turnClockMs = useRef(0);
  const expiration = useRef<string | null>(null);
  const invalidate = useCallback((code: string) => {
    blocked.current = code;
    setError(code); setPending(true); runtime.current?.pause();
  }, []);
  const failure = useCallback(() => invalidate('temporary-storage-failed'), [invalidate]);
  const geometryNow = useCallback(() => {
    const settings = latest.current.cameraStream?.getVideoTracks()[0]?.getSettings();
    return JSON.stringify({viewport_width: innerWidth, viewport_height: innerHeight, device_pixel_ratio: devicePixelRatio,
      screen_width: screen.width, screen_height: screen.height, orientation: innerWidth >= innerHeight ? 'landscape' : 'portrait',
      video_width: settings?.width, video_height: settings?.height});
  }, []);
  const devicesMatch = useCallback(() => {
    const camera = latest.current.cameraStream?.getVideoTracks()[0];
    const microphone = latest.current.microphoneStream?.getAudioTracks()[0];
    return Boolean(camera && microphone && camera.readyState !== 'ended' && microphone.readyState !== 'ended' &&
      camera.id === devices.current?.camera && microphone.id === devices.current?.microphone);
  }, []);

  const sampleRegion = useCallback(() => {
    const rect = document.querySelector<HTMLElement>('[data-interaction-area]')?.getBoundingClientRect();
    if (!rect || !runtime.current || sealed.current || closingTurn.current) return;
    const region = {xNormalized: Math.max(0, rect.x) / innerWidth, yNormalized: Math.max(0, rect.y) / innerHeight,
      widthNormalized: Math.max(0, Math.min(innerWidth, rect.right) - Math.max(0, rect.x)) / innerWidth,
      heightNormalized: Math.max(0, Math.min(innerHeight, rect.bottom) - Math.max(0, rect.y)) / innerHeight};
    if (!region.widthNormalized || !region.heightNormalized) return;
    const last = roi.current[roi.current.length - 1];
    if (last && Object.entries(region).every(([key, value]) => last[key] === value)) return;
    roi.current.push({timestampMs: runtime.current.elapsed(), ...region});
    void runtime.current.checkpoint({interaction_area_snapshots: [...roi.current]}).catch(failure);
  }, [failure]);

  // Start recording one student turn. Its session-clock origin is the running
  // offset of all preceding turns, so global ordering never sums block windows.
  const newTurn = useCallback(async () => {
    const {interviewId, cameraStream, microphoneStream} = latest.current;
    if (!interviewId || !cameraStream || !microphoneStream || !writer.current) throw new Error('Capture devices are unavailable');
    if (!devicesMatch()) {
      invalidate('capture-device-changed'); return;
    }
    if (geometry.current !== geometryNow()) {
      invalidate('capture-geometry-changed'); return;
    }
    setPending(true);
    const store = new InterviewTurnStore(turnScope(interviewId));
    await store.purgeExpired();
    turnClockMs.current = completedMs.current;
    const turn: LocalInterviewTurn = {id: crypto.randomUUID(), scope: store.scope, requestId: crypto.randomUUID(),
      mimeType: '', chunks: 0, confirmedEndMs: 0, expiresAt: expiration.current!, state: 'capturing',
      metadata: {capture_attempt_id: writer.current, order: order.current++, session_clock_ms: turnClockMs.current, speaker: 'student'}};
    const recorder = new InterviewTurnRecorder(store, turn, failure);
    runtime.current = recorder;
    roi.current = [];
    await recorder.start(cameraStream, microphoneStream);
    sampleRegion();
    if (disposed.current) {
      await recorder.stop(); return;
    }
    if (blocked.current || networkPaused.current || !navigator.onLine) recorder.pause();
    setStatus('recording');
    setPending(Boolean(blocked.current) || networkPaused.current || !navigator.onLine);
  }, [devicesMatch, geometryNow, invalidate, failure, sampleRegion]);

  const start = useCallback(async () => {
    const current = latest.current;
    if (starting.current || !current.enabled || !current.interviewId || !current.cameraStream || !current.microphoneStream) return;
    starting.current = true;
    const id = current.interviewId;
    setPending(true);
    try {
      if (geometry.current && geometry.current !== geometryNow()) {
        invalidate('capture-geometry-changed'); return;
      }
      blocked.current = null;
      setError(null);
      if (!writer.current) {
        forgetTurnQueue(id);
        startRequest.current ??= crypto.randomUUID();
        startBody.current ??= JSON.stringify({request_id: startRequest.current, resume_attempt_id: current.resumeAttemptId ?? undefined,
          capture_config: {mediaTransport: 'per_turn_v1', geometry: JSON.parse(geometryNow())}});
        startAbort.current = new AbortController();
        const segment = await turnJson<{segment_id: string; retention_expires_at: string; offset_ms: number}>(id, '/recording/segments', {
          method: 'POST', signal: startAbort.current.signal, headers: {'Content-Type': 'application/json'}, body: startBody.current});
        if (disposed.current) return;
        writer.current = segment.segment_id;
        setCaptureId(segment.segment_id);
        expiration.current = segment.retention_expires_at;
        completedMs.current = segment.offset_ms;
        geometry.current = JSON.stringify(JSON.parse(startBody.current).capture_config.geometry);
        devices.current = {camera: current.cameraStream.getVideoTracks()[0]?.id, microphone: current.microphoneStream.getAudioTracks()[0]?.id};
        if (geometry.current !== geometryNow()) {
          invalidate('capture-geometry-changed'); return;
        }
      }
      // Capture is armed; a student turn opens its own recorder on demand.
      setStatus('recording');
      setPending(Boolean(blocked.current) || networkPaused.current || !navigator.onLine);
    } catch (error) {
      if (disposed.current || startAbort.current?.signal.aborted) return;
      setStatus('failed');
      invalidate(error instanceof Error && error.message === 'capture_geometry_changed' ? 'capture-geometry-changed' : 'capture-start-failed');
    } finally {
      starting.current = false;
    }
  }, [geometryNow, invalidate]);

  useEffect(() => {
    if (!options.enabled || !options.interviewId || !options.cameraStream || !options.microphoneStream || started.current) return;
    started.current = true;
    serial.current = start();
  }, [options.enabled, options.interviewId, options.cameraStream, options.microphoneStream, start]);

  useEffect(() => {
    if (!options.enabled) return;
    const offline = () => {
      networkPaused.current = true;
      runtime.current?.pause(); setPending(true);
    };
    const online = () => {
      const id = latest.current.interviewId;
      if (!id || sealed.current || blocked.current) return;
      void turnJson<{active_segment_id: string | null}>(id, '/capture/state').then((state) => {
        if (state.active_segment_id !== writer.current) throw new Error('stale_capture');
        if (sealed.current || blocked.current) return;
        networkPaused.current = false;
        if (runtime.current?.resume()) setPending(false);
        else setPending(false);
      }).catch(failure);
    };
    window.addEventListener('offline', offline);
    window.addEventListener('online', online);
    const unsubscribe = subscribeTurnConnection(options.interviewId!, (connected) => {
      if (connected) online(); else offline();
    });
    const timer = setInterval(sampleRegion, 200);
    return () => {
      window.removeEventListener('offline', offline); window.removeEventListener('online', online); clearInterval(timer);
      unsubscribe();
    };
  }, [options.enabled, failure, sampleRegion]);
  useEffect(() => {
    if (!options.enabled) return;
    const check = () => {
      if (sealed.current || !geometry.current) return;
      if (geometry.current !== geometryNow()) invalidate('capture-geometry-changed');
      if (!devicesMatch()) invalidate('capture-device-changed');
    };
    const ended = () => {
      if (!sealed.current) invalidate('capture-device-changed');
    };
    const tracks = [...(options.cameraStream?.getVideoTracks() ?? []), ...(options.microphoneStream?.getAudioTracks() ?? [])];
    tracks.forEach((track) => track.addEventListener?.('ended', ended));
    check();
    const visibility = () => {
      if (document.hidden && !sealed.current && geometry.current) invalidate('capture-interrupted');
    };
    window.addEventListener('resize', check);
    window.addEventListener('orientationchange', check);
    document.addEventListener('visibilitychange', visibility);
    const timer = setInterval(check, 200);
    return () => {
      clearInterval(timer);
      window.removeEventListener('resize', check);
      window.removeEventListener('orientationchange', check);
      document.removeEventListener('visibilitychange', visibility);
      tracks.forEach((track) => track.removeEventListener?.('ended', ended));
    };
  }, [options.enabled, options.cameraStream, options.microphoneStream, devicesMatch, geometryNow, invalidate]);
  useEffect(() => {
    disposed.current = false;
    return () => {
      disposed.current = true;
      startAbort.current?.abort();
      void runtime.current?.stop().catch(() => undefined);
    };
  }, []);

  // Close the active student turn, bind it to its persisted message, upload it,
  // and advance the common session clock by its duration.
  const completeStudentTurn = useCallback((messageId: number) => {
    setPending(true);
    serial.current = serial.current.then(async () => {
      const current = runtime.current;
      const id = latest.current.interviewId;
      if (!current || !id) return;
      await current.flush();
      const end = current.elapsed();
      const metadata: TurnCaptureMetadata = {capture_attempt_id: writer.current!, order: current.turn.metadata.order!,
        message_id: messageId, speaker: 'student', session_clock_ms: turnClockMs.current,
        interaction_area_snapshots: roi.current, duration_ms: end};
      closingTurn.current = true;
      const closed = await current.close(metadata);
      completedMs.current = turnClockMs.current + (closed.metadata.duration_ms ?? end);
      runtime.current = null;
      closingTurn.current = false;
      void turnUploadQueue(id, () => writer.current).enqueue(closed).catch(failure);
    }).catch(failure);
  }, [failure]);

  const sealForEnding = useCallback(async () => {
    sealed.current = true;
    await serial.current;
    if (blocked.current) return false;
    const current = runtime.current;
    if (current) {
      try {
        await current.stop();
        await current.store.discardUnsent(current.turn);
      } catch {
        failure(); return false;
      }
      runtime.current = null;
    }
    setStatus('paused');
    setPending(false);
    return true;
  }, [failure]);
  const finalize = useCallback(async (preserveOnly = false) => {
    try {
      if (!await sealForEnding()) return false;
      const id = latest.current.interviewId!;
      const queue = turnUploadQueue(id, () => writer.current);
      await queue.drain();
      if (!preserveOnly) {
        const manifest = await getTurnManifest(id);
        await turnJson(id, '/recording/turns/finalize', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Capture-Segment': writer.current!},
          body: JSON.stringify({turn_media_ids: manifest.turns.map((item) => item.turn_media_id), missing_message_ids: latest.current.missingMessageIds ?? []})});
      }
      return true;
    } catch {
      failure(); return false;
    }
  }, [failure, sealForEnding]);
  const elapsedAt = useCallback(() => completedMs.current + (runtime.current?.elapsed() ?? 0), []);
  const stopForRecovery = useCallback(async () => {
    sealed.current = true;
    startAbort.current?.abort();
    setPending(true);
    await serial.current;
    try {
      await runtime.current?.stop();
    } catch {
      failure();
    }
    runtime.current = null;
    setStatus('paused');
  }, [failure]);
  const prepareStudentTurn = (timing?: SpeechTiming): StudentCaptureTiming => ({
    turn_media_id: runtime.current?.turn.id, capture_scope: runtime.current?.store.scope,
    start_ms: 0, end_ms: runtime.current?.elapsed(timing?.endedAt) ?? 0,
    input_source: timing?.inputSource ?? 'microphone', timing_source: 'turn_media', timing_quality: 'provisional', patient_roi_snapshots: [],
  });
  return {status, errorCode, syncPending, uploadProgress: 0, patientAudioLevel: 0, captureSegmentId: captureId,
    segmentId: status === 'recording' && !syncPending ? captureId : null, isCapturing: status === 'recording' && !syncPending,
    canResume: status === 'paused' && !blocked.current, canRestart: sealed.current,
    canRetryStart: errorCode === 'capture-start-failed', retryStart: start,
    canRestartWithCurrentGeometry: () => !blocked.current && devicesMatch() && geometry.current === geometryNow(),
    restartAfterCancel: () => {
      if (!devicesMatch() || geometry.current !== geometryNow()) {
        invalidate('capture-device-changed'); return Promise.resolve();
      }
      sealed.current = false;
      setPending(true);
      setStatus('recording');
      return serial.current;
    },
    pause: () => {
      runtime.current?.pause(); setStatus('paused');
    },
    resume: () => {
      if (!blocked.current && (runtime.current?.resume() ?? true)) setStatus('recording');
    },
    elapsedAt, sealForEnding, finalize, stopForRecovery, routePatientAudio: () => false, resumeAudioGraph: async () => undefined,
    // The patient turn is text-to-speech: it carries no captured media.
    beginPatientTurn: () => undefined,
    endPatientTurn: () => undefined,
    recordWrittenPatientTurn: () => undefined,
    // A student turn drives one recorder: open on speech start, close on submit.
    beginStudentTurn: () => {
      if (sealed.current || runtime.current) return;
      serial.current = serial.current.then(newTurn).catch(failure);
    },
    endStudentTurn: () => {
      runtime.current?.pause();
    },
    discardStudentTurn: () => {
      const current = runtime.current;
      if (!current) return;
      runtime.current = null;
      serial.current = serial.current.then(async () => {
        try {
          await current.stop();
          await current.store.discardUnsent(current.turn);
        } catch {
          // A partially captured, unsent turn that cannot be discarded is left
          // for expiry; it never becomes evidence without a message binding.
        }
      }).catch(() => undefined);
    },
    prepareStudentTurn,
    confirmStudentTurn: (timing: StudentCaptureTiming) => {
      if (timing.turn_media_id && runtime.current?.turn.id === timing.turn_media_id) {
        // messageId is supplied by recordStudentTurn; confirm only advances ROI.
        void runtime.current.checkpoint({interaction_area_snapshots: [...roi.current]}).catch(failure);
      }
    },
    recordStudentTurn: (messageId: number) => completeStudentTurn(messageId),
  };
};
