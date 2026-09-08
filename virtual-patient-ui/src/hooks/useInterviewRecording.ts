import {readDesignToken, readDesignNumber} from '../utils/designTokens';
import {useCallback, useEffect, useRef, useState} from 'react';
import {
  finalizeInterviewRecording,
  markInterviewRecordingUnavailable,
  saveInterviewTurn,
  startInterviewRecording,
} from '../services/recordings';
import {createRecordingBuffer, RecordingBuffer} from '../recording/RecordingBuffer';
import {
  CapturedMedia,
  RecordingAssetKind,
  RecordingStatus,
  SpeechTiming,
} from '../types/recording';

const VIDEO_WIDTH = 1280;
const VIDEO_HEIGHT = 720;
const VIDEO_FRAME_RATE = 30;
const RECORDER_TIMESLICE_MS = 5000;

type RecorderRuntime = {
  kind: RecordingAssetKind;
  recorder: MediaRecorder;
  buffer: RecordingBuffer;
  mimeType: string;
};

type PatientTurn = {
  messageId: number;
  sequence: number;
  transcript: string;
  startedAt: number;
};

type UseInterviewRecordingOptions = {
  interviewId?: number;
  enabled: boolean;
  cameraStream: MediaStream | null;
  cameraEnabled: boolean;
  microphoneEnabled: boolean;
  patientAudioEnabled: boolean;
  patientAvatar: string;
  patientName: string;
};

const selectMimeType = (candidates: string[]): string | null =>
  candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? null;

const extensionForMime = (mimeType: string): string =>
  mimeType.includes('mp4') ? (mimeType.startsWith('audio') ? '.m4a' : '.mp4') : '.webm';

const drawContainedVideo = (
  context: CanvasRenderingContext2D,
  video: HTMLVideoElement,
): void => {
  if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !video.videoWidth) return;
  const scale = Math.min(VIDEO_WIDTH / video.videoWidth, VIDEO_HEIGHT / video.videoHeight);
  const width = video.videoWidth * scale;
  const height = video.videoHeight * scale;
  context.drawImage(video, (VIDEO_WIDTH - width) / 2, (VIDEO_HEIGHT - height) / 2, width, height);
};

export const useInterviewRecording = ({
  interviewId,
  enabled,
  cameraStream,
  cameraEnabled,
  microphoneEnabled,
  patientAudioEnabled,
  patientAvatar,
  patientName,
}: UseInterviewRecordingOptions) => {
  const [status, setStatus] = useState<RecordingStatus>('idle');
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [patientAudioLevel, setPatientAudioLevel] = useState(0);
  const recordersRef = useRef<RecorderRuntime[]>([]);
  const cameraStreamRef = useRef(cameraStream);
  const cameraEnabledRef = useRef(cameraEnabled);
  const microphoneEnabledRef = useRef(microphoneEnabled);
  const patientAudioEnabledRef = useRef(patientAudioEnabled);
  const patientAvatarRef = useRef(patientAvatar);
  const patientNameRef = useRef(patientName);
  const patientSpeakingRef = useRef(false);
  const microphoneGainRef = useRef<GainNode | null>(null);
  const patientMonitorGainRef = useRef<GainNode | null>(null);
  const patientDestinationRef = useRef<MediaStreamAudioDestinationNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const patientAnalyserRef = useRef<AnalyserNode | null>(null);
  const patientLevelTimerRef = useRef<number | null>(null);
  const microphoneStreamRef = useRef<MediaStream | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const originRef = useRef<number | null>(null);
  const pausedAtRef = useRef<number | null>(null);
  const pausedDurationRef = useRef(0);
  const patientTurnsRef = useRef(new Map<number, PatientTurn>());
  const startingRef = useRef(false);
  const finalizedRef = useRef(false);
  const captureGenerationRef = useRef(0);
  const captureFailureRef = useRef<string | null>(null);
  const turnWritesRef = useRef(Promise.resolve());

  microphoneEnabledRef.current = microphoneEnabled;
  patientAudioEnabledRef.current = patientAudioEnabled;

  useEffect(() => {
    cameraStreamRef.current = cameraStream;
  }, [cameraStream]);
  useEffect(() => {
    cameraEnabledRef.current = cameraEnabled;
  }, [cameraEnabled]);
  useEffect(() => {
    patientAvatarRef.current = patientAvatar;
  }, [patientAvatar]);
  useEffect(() => {
    patientNameRef.current = patientName;
  }, [patientName]);
  useEffect(() => {
    if (microphoneGainRef.current) {
      microphoneGainRef.current.gain.setTargetAtTime(
        microphoneEnabled ? 1 : 0,
        microphoneGainRef.current.context.currentTime,
        0.01,
      );
    }
  }, [microphoneEnabled]);
  useEffect(() => {
    if (patientMonitorGainRef.current) {
      patientMonitorGainRef.current.gain.setTargetAtTime(
        patientAudioEnabled ? 1 : 0,
        patientMonitorGainRef.current.context.currentTime,
        0.01,
      );
    }
  }, [patientAudioEnabled]);

  const elapsedAt = useCallback((timestamp = performance.now()): number => {
    const origin = originRef.current;
    if (origin === null) return 0;
    const activePause = pausedAtRef.current === null ? 0 : Math.max(0, timestamp - pausedAtRef.current);
    return Math.max(0, Math.round(timestamp - origin - pausedDurationRef.current - activePause));
  }, []);

  const stopRuntime = useCallback(async (): Promise<CapturedMedia | null> => {
    if (recordersRef.current.length === 0) return null;
    const durationMs = elapsedAt();
    const runtimes = recordersRef.current;
    await Promise.all(runtimes.map((runtime) => new Promise<void>((resolve) => {
      if (runtime.recorder.state === 'inactive') {
        resolve();
        return;
      }
      runtime.recorder.addEventListener('stop', () => resolve(), {once: true});
      runtime.recorder.stop();
    })));
    const entries = await Promise.all(runtimes.map(async (runtime) => {
      const extension = extensionForMime(runtime.mimeType);
      const file = await runtime.buffer.finish(`${runtime.kind}${extension}`, runtime.mimeType);
      return [runtime.kind, file] as const;
    }));
    const files = Object.fromEntries(entries) as Record<RecordingAssetKind, File>;
    const sourceDurations = Object.fromEntries(
      entries.map(([kind]) => [kind, durationMs]),
    ) as Record<RecordingAssetKind, number>;
    return {
      durationMs,
      files,
      sourceDurations,
      captureConfig: {
        video: {width: VIDEO_WIDTH, height: VIDEO_HEIGHT, frameRate: VIDEO_FRAME_RATE},
        audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true},
        clock: 'performance.now',
        studentTiming: 'browser-speech-events-provisional',
      },
    };
  }, [elapsedAt]);

  const releaseResources = useCallback(async (discardBuffers: boolean) => {
    if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current);
    animationFrameRef.current = null;
    if (patientLevelTimerRef.current !== null) window.clearInterval(patientLevelTimerRef.current);
    patientLevelTimerRef.current = null;
    patientAnalyserRef.current = null;
    setPatientAudioLevel(0);
    microphoneStreamRef.current?.getTracks().forEach((track) => track.stop());
    microphoneStreamRef.current = null;
    const runtimes = recordersRef.current;
    recordersRef.current = [];
    runtimes.forEach(({recorder}) => {
      if (recorder.state !== 'inactive') recorder.stop();
      recorder.stream.getTracks().forEach((track) => track.stop());
    });
    const audioContext = audioContextRef.current;
    audioContextRef.current = null;
    const closing = audioContext?.close().catch(() => undefined);
    if (discardBuffers) {
      await Promise.all(runtimes.map((runtime) => runtime.buffer.discard()));
    }
    await closing;
    microphoneGainRef.current = null;
    patientMonitorGainRef.current = null;
    patientDestinationRef.current = null;
  }, []);

  const start = useCallback(async () => {
    if (!enabled || !interviewId || startingRef.current || recordersRef.current.length > 0) return;
    startingRef.current = true;
    const generation = captureGenerationRef.current;
    finalizedRef.current = false;
    captureFailureRef.current = null;
    setErrorCode(null);
    if (!window.MediaRecorder || !window.AudioContext || !HTMLCanvasElement.prototype.captureStream) {
      setStatus('failed');
      setErrorCode('unsupported');
      await markInterviewRecordingUnavailable(interviewId, 'browser-capture-unsupported').catch(() => undefined);
      startingRef.current = false;
      return;
    }

    const videoMime = selectMimeType(['video/webm;codecs=vp8', 'video/webm', 'video/mp4']);
    const audioMime = selectMimeType(['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']);
    if (!videoMime || !audioMime) {
      setStatus('failed');
      setErrorCode('unsupported-codec');
      await markInterviewRecordingUnavailable(interviewId, 'recording-codec-unsupported').catch(() => undefined);
      startingRef.current = false;
      return;
    }

    try {
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const studentDestination = audioContext.createMediaStreamDestination();
      const patientDestination = audioContext.createMediaStreamDestination();
      patientDestinationRef.current = patientDestination;
      const studentSilence = audioContext.createConstantSource();
      const patientSilence = audioContext.createConstantSource();
      const studentSilenceGain = audioContext.createGain();
      const patientSilenceGain = audioContext.createGain();
      studentSilenceGain.gain.value = 0;
      patientSilenceGain.gain.value = 0;
      studentSilence.connect(studentSilenceGain).connect(studentDestination);
      patientSilence.connect(patientSilenceGain).connect(patientDestination);
      studentSilence.start();
      patientSilence.start();

      try {
        const microphoneStream = await navigator.mediaDevices.getUserMedia({
          video: false,
          audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true},
        });
        if (generation !== captureGenerationRef.current) {
          microphoneStream.getTracks().forEach((track) => track.stop());
          return;
        }
        microphoneStreamRef.current = microphoneStream;
        const microphoneSource = audioContext.createMediaStreamSource(microphoneStream);
        const microphoneGain = audioContext.createGain();
        microphoneGain.gain.value = microphoneEnabledRef.current ? 1 : 0;
        microphoneSource.connect(microphoneGain).connect(studentDestination);
        microphoneGainRef.current = microphoneGain;
      } catch {
        setErrorCode('microphone-unavailable');
      }

      if (generation !== captureGenerationRef.current) return;
      const monitorGain = audioContext.createGain();
      monitorGain.gain.value = patientAudioEnabledRef.current ? 1 : 0;
      monitorGain.connect(audioContext.destination);
      patientMonitorGainRef.current = monitorGain;

      const studentCanvas = document.createElement('canvas');
      const patientCanvas = document.createElement('canvas');
      studentCanvas.width = patientCanvas.width = VIDEO_WIDTH;
      studentCanvas.height = patientCanvas.height = VIDEO_HEIGHT;
      const studentContext = studentCanvas.getContext('2d');
      const patientContext = patientCanvas.getContext('2d');
      if (!studentContext || !patientContext) throw new Error('Canvas context unavailable');
      const cameraVideo = document.createElement('video');
      cameraVideo.muted = true;
      cameraVideo.playsInline = true;
      let attachedCameraStream: MediaStream | null = null;
      const avatar = new Image();
      avatar.src = patientAvatarRef.current;

      const recordingTheme = {
        studentBackground: readDesignToken('--recording-student-background'),
        patientBackground: readDesignToken('--recording-patient-background'),
        mutedText: readDesignToken('--recording-muted-text'),
        text: readDesignToken('--recording-text'),
        speaking: readDesignToken('--recording-speaking'),
        idle: readDesignToken('--recording-idle'),
        noticeFont: readDesignToken('--recording-notice-font'),
        nameFont: readDesignToken('--recording-name-font'),
        avatarRadius: readDesignNumber('--recording-avatar-radius'),
        ringOffset: readDesignNumber('--recording-ring-offset'),
        speakingWidth: readDesignNumber('--recording-speaking-width'),
        idleWidth: readDesignNumber('--recording-idle-width'),
        nameBottom: readDesignNumber('--recording-name-bottom'),
      };
      const draw = () => {
        if (cameraStreamRef.current !== attachedCameraStream) {
          attachedCameraStream = cameraStreamRef.current;
          cameraVideo.srcObject = attachedCameraStream;
          if (attachedCameraStream) void cameraVideo.play().catch(() => undefined);
        }
        studentContext.fillStyle = recordingTheme.studentBackground;
        studentContext.fillRect(0, 0, VIDEO_WIDTH, VIDEO_HEIGHT);
        if (cameraEnabledRef.current && attachedCameraStream) drawContainedVideo(studentContext, cameraVideo);
        else {
          studentContext.fillStyle = recordingTheme.mutedText;
          studentContext.font = recordingTheme.noticeFont;
          studentContext.textAlign = 'center';
          studentContext.fillText('Camera unavailable', VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2);
        }

        patientContext.fillStyle = recordingTheme.patientBackground;
        patientContext.fillRect(0, 0, VIDEO_WIDTH, VIDEO_HEIGHT);
        const radius = recordingTheme.avatarRadius;
        patientContext.save();
        patientContext.beginPath();
        patientContext.arc(VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2, radius, 0, Math.PI * 2);
        patientContext.clip();
        if (avatar.complete) patientContext.drawImage(avatar, VIDEO_WIDTH / 2 - radius, VIDEO_HEIGHT / 2 - radius, radius * 2, radius * 2);
        patientContext.restore();
        patientContext.strokeStyle = patientSpeakingRef.current ? recordingTheme.speaking : recordingTheme.idle;
        patientContext.lineWidth = patientSpeakingRef.current ? recordingTheme.speakingWidth : recordingTheme.idleWidth;
        patientContext.beginPath();
        patientContext.arc(VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2, radius + recordingTheme.ringOffset, 0, Math.PI * 2);
        patientContext.stroke();
        patientContext.fillStyle = recordingTheme.text;
        patientContext.font = recordingTheme.nameFont;
        patientContext.textAlign = 'center';
        patientContext.fillText(patientNameRef.current, VIDEO_WIDTH / 2, VIDEO_HEIGHT - recordingTheme.nameBottom);
        animationFrameRef.current = requestAnimationFrame(draw);
      };
      draw();

      const streams: Record<RecordingAssetKind, MediaStream> = {
        student_audio: studentDestination.stream,
        patient_audio: patientDestination.stream,
        student_video: studentCanvas.captureStream(VIDEO_FRAME_RATE),
        patient_video: patientCanvas.captureStream(VIDEO_FRAME_RATE),
      };
      const mimeTypes: Record<RecordingAssetKind, string> = {
        student_audio: audioMime,
        patient_audio: audioMime,
        student_video: videoMime,
        patient_video: videoMime,
      };
      const runtimes = await Promise.all((Object.keys(streams) as RecordingAssetKind[]).map(async (kind) => {
        const buffer = await createRecordingBuffer(`${interviewId}-${kind}`);
        const recorder = new MediaRecorder(streams[kind], {
          mimeType: mimeTypes[kind],
          ...(kind.endsWith('video') ? {videoBitsPerSecond: 2_500_000} : {audioBitsPerSecond: 96_000}),
        });
        recorder.addEventListener('dataavailable', (event) => {
          if (event.data.size > 0) {
            void buffer.append(event.data).catch(() => {
              captureFailureRef.current = 'temporary-storage-failed';
              setErrorCode('temporary-storage-failed');
            });
          }
        });
        recorder.addEventListener('error', () => {
          captureFailureRef.current = 'media-recorder-failed';
          setErrorCode('media-recorder-failed');
        });
        return {kind, recorder, buffer, mimeType: mimeTypes[kind]};
      }));
      if (generation !== captureGenerationRef.current) {
        await Promise.all(runtimes.map(async ({recorder, buffer}) => {
          recorder.stream.getTracks().forEach((track) => track.stop());
          await buffer.discard();
        }));
        return;
      }
      recordersRef.current = runtimes;
      originRef.current = performance.now();
      pausedDurationRef.current = 0;
      pausedAtRef.current = null;
      runtimes.forEach((runtime) => runtime.recorder.start(RECORDER_TIMESLICE_MS));
      await startInterviewRecording(interviewId, new Date().toISOString(), {
        video: {width: VIDEO_WIDTH, height: VIDEO_HEIGHT, frameRate: VIDEO_FRAME_RATE},
        audioMime,
        videoMime,
        clock: 'performance.now',
      });
      if (generation !== captureGenerationRef.current) return;
      setStatus('recording');
    } catch {
      if (generation !== captureGenerationRef.current) return;
      setStatus('failed');
      setErrorCode('capture-start-failed');
      await releaseResources(true);
      await markInterviewRecordingUnavailable(interviewId, 'capture-start-failed').catch(() => undefined);
    } finally {
      startingRef.current = false;
    }
  }, [enabled, interviewId, releaseResources]);

  useEffect(() => {
    if (enabled) void start();
  }, [enabled, start]);

  const pause = useCallback(() => {
    if (status !== 'recording') return;
    pausedAtRef.current = performance.now();
    recordersRef.current.forEach(({recorder}) => {
      if (recorder.state === 'recording') recorder.pause();
    });
    setStatus('paused');
  }, [status]);

  const resume = useCallback(() => {
    if (status !== 'paused') return;
    if (pausedAtRef.current !== null) pausedDurationRef.current += performance.now() - pausedAtRef.current;
    pausedAtRef.current = null;
    recordersRef.current.forEach(({recorder}) => {
      if (recorder.state === 'paused') recorder.resume();
    });
    setStatus('recording');
  }, [status]);

  const routePatientAudio = useCallback((audio: HTMLAudioElement): boolean => {
    const context = audioContextRef.current;
    const destination = patientDestinationRef.current;
    const monitor = patientMonitorGainRef.current;
    if (!context || !destination || !monitor) return false;
    try {
      const source = context.createMediaElementSource(audio);
      const analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      patientAnalyserRef.current = analyser;
      source.connect(analyser);
      analyser.connect(destination);
      analyser.connect(monitor);
      if (patientLevelTimerRef.current !== null) window.clearInterval(patientLevelTimerRef.current);
      patientLevelTimerRef.current = window.setInterval(() => {
        const samples = new Float32Array(analyser.fftSize);
        analyser.getFloatTimeDomainData(samples);
        const rms = Math.sqrt(
          samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length,
        );
        setPatientAudioLevel(Math.min(1, rms / 0.16));
      }, 60);
      void context.resume();
      return true;
    } catch {
      return false;
    }
  }, []);

  const resumeAudioGraph = useCallback(async (): Promise<void> => {
    const context = audioContextRef.current;
    if (context && context.state !== 'running') await context.resume();
  }, []);

  const beginPatientTurn = useCallback((messageId: number, sequence: number, transcript: string) => {
    patientSpeakingRef.current = true;
    patientTurnsRef.current.set(messageId, {messageId, sequence, transcript, startedAt: performance.now()});
  }, []);

  const endPatientTurn = useCallback((messageId: number) => {
    patientSpeakingRef.current = false;
    if (patientLevelTimerRef.current !== null) window.clearInterval(patientLevelTimerRef.current);
    patientLevelTimerRef.current = null;
    patientAnalyserRef.current = null;
    setPatientAudioLevel(0);
    const turn = patientTurnsRef.current.get(messageId);
    if (!turn || !interviewId) return;
    patientTurnsRef.current.delete(messageId);
    turnWritesRef.current = turnWritesRef.current
      .then(() => saveInterviewTurn(interviewId, messageId, {
        speaker: 'patient',
        sequence: turn.sequence,
        startMs: elapsedAt(turn.startedAt),
        endMs: elapsedAt(),
        transcript: turn.transcript,
        inputSource: 'tts',
        timingSource: 'tts_playback',
        timingQuality: 'measured',
      }))
      .catch(() => setErrorCode('turn-storage-failed'));
  }, [elapsedAt, interviewId]);

  const recordStudentTurn = useCallback((
    messageId: number,
    sequence: number,
    transcript: string,
    timing?: SpeechTiming,
  ) => {
    if (!interviewId) return;
    const now = performance.now();
    turnWritesRef.current = turnWritesRef.current
      .then(() => saveInterviewTurn(interviewId, messageId, {
        speaker: 'student',
        sequence,
        startMs: elapsedAt(timing?.startedAt ?? now),
        endMs: elapsedAt(timing?.endedAt ?? now),
        transcript,
        inputSource: timing?.inputSource ?? (timing ? 'browser_speech' : 'text_input'),
        timingSource: timing?.timingSource ?? (timing ? 'browser_speech_events' : 'text_input'),
        timingQuality: timing ? 'provisional' : 'estimated',
      }))
      .catch(() => setErrorCode('turn-storage-failed'));
  }, [elapsedAt, interviewId]);

  const finalize = useCallback(async (): Promise<boolean> => {
    if (!interviewId || finalizedRef.current) return status === 'ready' || status === 'partial';
    finalizedRef.current = true;
    setStatus('finalizing');
    try {
      await turnWritesRef.current;
      const captured = await stopRuntime();
      if (!captured) throw new Error('No captured media');
      if (captureFailureRef.current) throw new Error(captureFailureRef.current);
      const response = await finalizeInterviewRecording(interviewId, captured, setUploadProgress);
      setStatus(response.recordingStatus);
      await releaseResources(true);
      return response.recordingStatus === 'ready' || response.recordingStatus === 'partial';
    } catch (error) {
      const durationMs = elapsedAt();
      const failureCode = captureFailureRef.current ?? 'recording-upload-failed';
      console.error('Interview recording finalization failed in the browser', {
        interviewId,
        failureCode,
        durationMs,
        error: error instanceof Error ? error.message : 'Unknown error',
      });
      setStatus('failed');
      setErrorCode(captureFailureRef.current ?? 'upload-failed');
      await markInterviewRecordingUnavailable(interviewId, failureCode, durationMs).catch(() => undefined);
      await releaseResources(true);
      return false;
    }
  }, [elapsedAt, interviewId, releaseResources, status, stopRuntime]);

  useEffect(() => () => {
    captureGenerationRef.current += 1;
    recordersRef.current.forEach(({recorder}) => {
      if (recorder.state !== 'inactive') recorder.stop();
    });
    void releaseResources(true);
  }, [releaseResources]);

  return {
    status,
    errorCode,
    uploadProgress,
    patientAudioLevel,
    isCapturing: status === 'recording' || status === 'paused',
    pause,
    resume,
    finalize,
    elapsedAt,
    routePatientAudio,
    resumeAudioGraph,
    beginPatientTurn,
    endPatientTurn,
    recordStudentTurn,
  };
};
