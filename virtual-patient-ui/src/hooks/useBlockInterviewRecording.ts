import {useCallback, useEffect, useRef, useState} from 'react';
import {InterviewBlockRecorder} from '../recording/InterviewBlockRecorder';
import {InterviewBlockStore, type BlockMetadata, type LocalInterviewBlock} from '../recording/InterviewBlockStore';
import {blockJson, blockScope, blockUploadQueue, getBlockManifest, forgetBlockQueue, subscribeBlockConnection} from '../services/recordings/blocks';
import type {UseInterviewRecordingOptions} from './useInterviewRecording';
import type {RecordingStatus, SpeechTiming, StudentCaptureTiming} from '../types/recording';

export const useBlockInterviewRecording = (options: UseInterviewRecordingOptions) => {
  const [status, setStatus] = useState<RecordingStatus>('idle');
  const [syncPending, setPending] = useState(false);
  const [errorCode, setError] = useState<string | null>(null);
  const [captureId, setCaptureId] = useState<string | null>(null);
  const runtime = useRef<InterviewBlockRecorder | null>(null);
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
    if (!rect || !runtime.current || sealed.current) return;
    const region = {xNormalized: Math.max(0, rect.x) / innerWidth, yNormalized: Math.max(0, rect.y) / innerHeight,
      widthNormalized: Math.max(0, Math.min(innerWidth, rect.right) - Math.max(0, rect.x)) / innerWidth,
      heightNormalized: Math.max(0, Math.min(innerHeight, rect.bottom) - Math.max(0, rect.y)) / innerHeight};
    if (!region.widthNormalized || !region.heightNormalized) return;
    const last = roi.current[roi.current.length - 1];
    if (last && Object.entries(region).every(([key, value]) => last[key] === value)) return;
    roi.current.push({timestampMs: runtime.current.elapsed(), ...region});
  }, []);

  const newBlock = useCallback(async () => {
    const {interviewId, cameraStream, microphoneStream} = latest.current;
    if (!interviewId || !cameraStream || !microphoneStream || !writer.current) throw new Error('Capture devices are unavailable');
    if (!devicesMatch()) {
      invalidate('capture-device-changed'); return;
    }
    if (geometry.current !== geometryNow()) {
      invalidate('capture-geometry-changed'); return;
    }
    setPending(true);
    const store = new InterviewBlockStore(blockScope(interviewId));
    await store.purgeExpired();
    const block: LocalInterviewBlock = {id: crypto.randomUUID(), scope: store.scope, requestId: crypto.randomUUID(),
      mimeType: '', chunks: 0, confirmedEndMs: 0, expiresAt: expiration.current!, state: 'capturing',
      metadata: {capture_attempt_id: writer.current, order: order.current++}};
    const recorder = new InterviewBlockRecorder(store, block, failure);
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
  const expiration = useRef<string | null>(null);

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
        forgetBlockQueue(id);
        startRequest.current ??= crypto.randomUUID();
        startBody.current ??= JSON.stringify({request_id: startRequest.current, resume_attempt_id: current.resumeAttemptId ?? undefined,
          capture_config: {mediaTransport: 'reusable_blocks_v1', geometry: JSON.parse(geometryNow())}});
        startAbort.current = new AbortController();
        const segment = await blockJson<{segment_id: string; retention_expires_at: string; offset_ms: number}>(id, '/recording/segments', {
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
      if (runtime.current) {
        await runtime.current.stop();
        const existing = (await runtime.current.store.list()).find((item) => item.id === runtime.current?.block.id);
        if (existing) await runtime.current.store.discardUnsent(existing);
        runtime.current = null;
      }
      await newBlock();
    } catch (error) {
      if (disposed.current || startAbort.current?.signal.aborted) return;
      setStatus('failed');
      invalidate(error instanceof Error && error.message === 'capture_geometry_changed' ? 'capture-geometry-changed' : 'capture-start-failed');
    } finally {
      starting.current = false;
    }
  }, [geometryNow, invalidate, newBlock]);
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
      void blockJson<{active_segment_id: string | null}>(id, '/capture/state').then((state) => {
        if (state.active_segment_id !== writer.current) throw new Error('stale_capture');
        if (sealed.current || blocked.current) return;
        networkPaused.current = false;
        if (runtime.current?.resume()) setPending(false);
      }).catch(failure);
    };
    window.addEventListener('offline', offline);
    window.addEventListener('online', online);
    const unsubscribe = subscribeBlockConnection(options.interviewId!, (connected) => {
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

  const completeBlock = useCallback((patientId: number, written = false) => {
    setPending(true);
    serial.current = serial.current.then(async () => {
      const current = runtime.current;
      const id = latest.current.interviewId;
      if (!current || !id) throw new Error('Active block is unavailable');
      await current.flush();
      const persisted = (await current.store.list()).find((item) => item.id === current.block.id);
      if (!persisted) throw new Error('Active block checkpoint is unavailable');
      const end = current.elapsed();
      const playbackStart = persisted.metadata.patient_playback?.start_ms;
      const metadata: BlockMetadata = {capture_attempt_id: writer.current!, order: current.block.metadata.order!,
        student_message_id: persisted.metadata.student_message_id ?? null, patient_message_id: patientId,
        student_speech: persisted.metadata.student_speech ?? null,
        patient_playback: playbackStart == null ? null : {start_ms: playbackStart, end_ms: end},
        patient_audio_missing: written, patient_playback_complete: true, recovery: Boolean(latest.current.resumeAttemptId && !persisted.metadata.student_message_id),
        interaction_area_snapshots: roi.current, duration_ms: end};
      const closed = await current.close(metadata);
      completedMs.current += closed.metadata.duration_ms!;
      runtime.current = null;
      void blockUploadQueue(id, () => writer.current).enqueue(closed).catch(failure);
      if (!sealed.current) await newBlock();
    }).catch(failure);
  }, [newBlock, failure]);

  const sealForEnding = useCallback(async () => {
    sealed.current = true;
    await serial.current;
    if (blocked.current) return false;
    const current = runtime.current;
    if (current) {
      try {
        await current.stop();
        await current.store.discardUnsent(current.block);
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
      const queue = blockUploadQueue(id, () => writer.current);
      await queue.drain();
      if (!preserveOnly) {
        const manifest = await getBlockManifest(id);
        await blockJson(id, '/recording/blocks/finalize', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Capture-Segment': writer.current!},
          body: JSON.stringify({block_ids: manifest.blocks.map((item) => item.block_id), missing_message_ids: latest.current.missingMessageIds ?? []})});
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
    block_id: runtime.current?.block.id, block_scope: runtime.current?.store.scope,
    start_ms: runtime.current?.elapsed(timing?.startedAt) ?? 0, end_ms: runtime.current?.elapsed(timing?.endedAt) ?? 0,
    input_source: timing?.inputSource ?? 'microphone', timing_source: 'block_speech', timing_quality: 'provisional', patient_roi_snapshots: [],
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
      serial.current = serial.current.then(newBlock).catch(failure);
      return serial.current;
    },
    pause: () => {
      runtime.current?.pause(); setStatus('paused');
    },
    resume: () => {
      if (!blocked.current && runtime.current?.resume()) setStatus('recording');
    },
    elapsedAt, sealForEnding, finalize, stopForRecovery, routePatientAudio: () => false, resumeAudioGraph: async () => undefined,
    beginPatientTurn: (messageId: number) => {
      const current = runtime.current;
      if (current) {
        void current.checkpoint({patient_message_id: messageId,
          patient_playback: {start_ms: current.elapsed(), end_ms: current.elapsed()}}).catch(failure);
      }
    },
    endPatientTurn: (messageId: number, complete = false) => {
      if (complete) completeBlock(messageId);
    },
    recordWrittenPatientTurn: (messageId: number) => completeBlock(messageId, true),
    beginStudentTurn: () => undefined, endStudentTurn: () => undefined, discardStudentTurn: () => undefined,
    prepareStudentTurn, confirmStudentTurn: () => undefined,
    recordStudentTurn: () => undefined,
  };
};
