import {useCallback, useEffect, useRef, useState} from 'react';
import {FaceDetection} from '@mediapipe/face_detection';
import {CalibrationResultPayload} from '../services/interviews';
import {selectVideoMimeType} from '../utils/mediaRecorder';

const CALIBRATION_DURATION_MS = 20_000;
const VOICE_ACTIVITY_RMS = 0.012;
const LOW_SIGNAL_RMS = 0.02;
const HIGH_SIGNAL_RMS = 0.15;
const CLIPPING_AMPLITUDE = 0.98;
const FACE_SAMPLE_INTERVAL_MS = 250;
const MIN_FACE_DETECTION_RATE = 80;

export type CalibrationPhase = 'idle' | 'recording' | 'complete' | 'error';

export const useTechnicalCalibration = (
  microphoneStream: MediaStream | null,
  cameraStream: MediaStream | null,
) => {
  const [phase, setPhase] = useState<CalibrationPhase>('idle');
  const [audioLevel, setAudioLevel] = useState(0);
  const [voiceDetected, setVoiceDetected] = useState(false);
  const [faceDetected, setFaceDetected] = useState(false);
  const [faceDetectionRate, setFaceDetectionRate] = useState(0);
  const [remainingMs, setRemainingMs] = useState(CALIBRATION_DURATION_MS);
  const [result, setResult] = useState<CalibrationResultPayload | null>(null);
  // The recorded calibration media, assembled once recording finishes. The same
  // ~20s recording that drives the device checks is reused to derive the
  // personal baseline; nothing extra is captured. Kept only long enough to be
  // uploaded, then cleared on reset.
  const [media, setMedia] = useState<{blob: Blob; mimeType: string} | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);
  const timerRef = useRef<number | null>(null);
  const faceTimerRef = useRef<number | null>(null);
  const faceDetectorRef = useRef<FaceDetection | null>(null);
  const faceVideoRef = useRef<HTMLVideoElement | null>(null);
  const faceRequestPendingRef = useRef(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const temporaryStreamRef = useRef<MediaStream | null>(null);
  const recordingRef = useRef(false);
  // Buffers the MediaRecorder chunks so the recorded media can be reused for
  // baseline derivation. Previously discarded in `ondataavailable`.
  const chunksRef = useRef<Blob[]>([]);
  const recorderMimeRef = useRef<string>('');
  const samplesRef = useRef({sum: 0, count: 0, peak: 0, voiceDetected: false});
  const faceSamplesRef = useRef({total: 0, detected: 0});

  const stopTemporaryRecording = useCallback(() => {
    const recorder = recorderRef.current;
    recorderRef.current = null;
    // Stopping flushes a final `dataavailable` and then fires `onstop`, where
    // the buffered chunks are assembled into the reusable calibration blob.
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    temporaryStreamRef.current?.getTracks().forEach((track) => track.stop());
    temporaryStreamRef.current = null;
    if (faceTimerRef.current !== null) window.clearInterval(faceTimerRef.current);
    faceTimerRef.current = null;
    faceRequestPendingRef.current = false;
    if (faceVideoRef.current) {
      faceVideoRef.current.pause();
      faceVideoRef.current.srcObject = null;
    }
    faceVideoRef.current = null;
  }, []);

  useEffect(() => {
    if (!microphoneStream?.active || typeof AudioContext === 'undefined') {
      setAudioLevel(0);
      return undefined;
    }
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 2048;
    context.createMediaStreamSource(microphoneStream).connect(analyser);
    audioContextRef.current = context;
    analyserRef.current = analyser;
    const data = new Float32Array(analyser.fftSize);

    const analyse = () => {
      analyser.getFloatTimeDomainData(data);
      let squareSum = 0;
      let peak = 0;
      data.forEach((sample) => {
        squareSum += sample * sample;
        peak = Math.max(peak, Math.abs(sample));
      });
      const rms = Math.sqrt(squareSum / data.length);
      setAudioLevel(Math.min(1, rms / 0.12));
      if (recordingRef.current) {
        const aggregate = samplesRef.current;
        aggregate.sum += rms;
        aggregate.count += 1;
        aggregate.peak = Math.max(aggregate.peak, peak);
        if (!aggregate.voiceDetected && rms >= VOICE_ACTIVITY_RMS) {
          aggregate.voiceDetected = true;
          setVoiceDetected(true);
        }
      }
      animationRef.current = requestAnimationFrame(analyse);
    };
    void context.resume();
    analyse();
    return () => {
      if (animationRef.current !== null) cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
      analyserRef.current = null;
      audioContextRef.current = null;
      void context.close();
    };
  }, [microphoneStream]);

  const finish = useCallback(() => {
    recordingRef.current = false;
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = null;
    stopTemporaryRecording();
    const audio = samplesRef.current;
    const meanRms = audio.count ? audio.sum / audio.count : 0;
    const inputLevel = meanRms < LOW_SIGNAL_RMS
      ? 'low'
      : meanRms > HIGH_SIGNAL_RMS
        ? 'high'
        : 'adequate';
    const clippingDetected = audio.peak >= CLIPPING_AMPLITUDE;
    const faceSamples = faceSamplesRef.current;
    const finalFaceDetectionRate = faceSamples.total
      ? (faceSamples.detected / faceSamples.total) * 100
      : 0;
    const finalFaceDetected = finalFaceDetectionRate >= MIN_FACE_DETECTION_RATE;
    const videoTrack = cameraStream?.getVideoTracks()[0];
    const audioTrack = microphoneStream?.getAudioTracks()[0];
    const streamActive = Boolean(videoTrack?.readyState === 'live');
    const microphoneActive = Boolean(
      microphoneStream?.active && audioTrack?.readyState === 'live',
    );
    const nextResult: CalibrationResultPayload = {
      version: 'technical_v2',
      status: audio.voiceDetected && microphoneActive && streamActive &&
        inputLevel === 'adequate' && !clippingDetected && finalFaceDetected
        ? 'passed'
        : 'failed',
      durationMs: CALIBRATION_DURATION_MS,
      recordingSupported: true,
      audio: {
        microphoneAvailable: Boolean(microphoneStream?.getAudioTracks().length),
        streamActive: microphoneActive,
        voiceDetected: audio.voiceDetected,
        inputLevel,
        clippingDetected,
      },
      video: {
        cameraAvailable: Boolean(videoTrack),
        streamActive,
        faceDetected: finalFaceDetected,
        faceDetectionRate: finalFaceDetectionRate,
        qualityStatus: streamActive && finalFaceDetected ? 'adequate' : 'inadequate',
      },
      personalBaseline: null,
    };
    setRemainingMs(0);
    setResult(nextResult);
    setFaceDetected(finalFaceDetected);
    setFaceDetectionRate(finalFaceDetectionRate);
    setPhase('complete');
  }, [cameraStream, microphoneStream, stopTemporaryRecording]);

  const start = useCallback(async () => {
    const videoMime = selectVideoMimeType();
    if (!microphoneStream?.active || !cameraStream?.active || !videoMime) {
      setPhase('error');
      return;
    }
    await audioContextRef.current?.resume();
    stopTemporaryRecording();
    if (!faceDetectorRef.current) {
      const detector = new FaceDetection({
        locateFile: (file) => `/mediapipe/face_detection/${file}`,
      });
      detector.setOptions({model: 'short', minDetectionConfidence: 0.5});
      detector.onResults((faceResults) => {
        const samples = faceSamplesRef.current;
        samples.total += 1;
        if (faceResults.detections.length > 0) samples.detected += 1;
        const rate = (samples.detected / samples.total) * 100;
        setFaceDetected(faceResults.detections.length > 0);
        setFaceDetectionRate(rate);
      });
      try {
        await detector.initialize();
        faceDetectorRef.current = detector;
      } catch {
        await detector.close().catch(() => undefined);
        setPhase('error');
        return;
      }
    }
    const temporaryStream = new MediaStream([
      ...microphoneStream.getAudioTracks().map((track) => track.clone()),
      ...cameraStream.getVideoTracks().map((track) => track.clone()),
    ]);
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(temporaryStream, {mimeType: videoMime});
    } catch {
      temporaryStream.getTracks().forEach((track) => track.stop());
      setPhase('error');
      return;
    }
    chunksRef.current = [];
    recorderMimeRef.current = videoMime;
    setMedia(null);
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      const chunks = chunksRef.current;
      chunksRef.current = [];
      if (chunks.length === 0) return;
      // The recorder produces a single container with both the microphone and
      // camera tracks; it is reused as the baseline media (uploaded as `video`
      // so both extractors can run on it).
      const mimeType = recorderMimeRef.current || chunks[0].type || 'video/webm';
      setMedia({blob: new Blob(chunks, {type: mimeType}), mimeType});
    };
    recorder.onerror = () => {
      recordingRef.current = false;
      setPhase('error');
      stopTemporaryRecording();
    };
    recorderRef.current = recorder;
    temporaryStreamRef.current = temporaryStream;
    samplesRef.current = {sum: 0, count: 0, peak: 0, voiceDetected: false};
    setVoiceDetected(false);
    faceSamplesRef.current = {total: 0, detected: 0};
    setFaceDetected(false);
    setFaceDetectionRate(0);
    setResult(null);
    setRemainingMs(CALIBRATION_DURATION_MS);
    setPhase('recording');
    recordingRef.current = true;
    const startedAt = performance.now();
    recorder.start(1_000);
    const faceVideo = document.createElement('video');
    faceVideo.muted = true;
    faceVideo.playsInline = true;
    faceVideo.srcObject = cameraStream;
    faceVideoRef.current = faceVideo;
    await faceVideo.play();
    faceTimerRef.current = window.setInterval(() => {
      if (faceRequestPendingRef.current || faceVideo.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
      faceRequestPendingRef.current = true;
      void faceDetectorRef.current?.send({image: faceVideo})
        .catch(() => setPhase('error'))
        .finally(() => {
          faceRequestPendingRef.current = false;
        });
    }, FACE_SAMPLE_INTERVAL_MS);
    timerRef.current = window.setInterval(() => {
      const nextRemaining = Math.max(0, CALIBRATION_DURATION_MS - (performance.now() - startedAt));
      setRemainingMs(nextRemaining);
      if (nextRemaining === 0) finish();
    }, 100);
  }, [cameraStream, finish, microphoneStream, stopTemporaryRecording]);

  const reset = useCallback(() => {
    recordingRef.current = false;
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = null;
    stopTemporaryRecording();
    samplesRef.current = {sum: 0, count: 0, peak: 0, voiceDetected: false};
    setVoiceDetected(false);
    faceSamplesRef.current = {total: 0, detected: 0};
    setFaceDetected(false);
    setFaceDetectionRate(0);
    setRemainingMs(CALIBRATION_DURATION_MS);
    setResult(null);
    chunksRef.current = [];
    setMedia(null);
    setPhase('idle');
  }, [stopTemporaryRecording]);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    stopTemporaryRecording();
    void faceDetectorRef.current?.close();
    faceDetectorRef.current = null;
  }, [stopTemporaryRecording]);

  return {
    phase,
    audioLevel,
    voiceDetected,
    faceDetected,
    faceDetectionRate,
    remainingMs,
    result,
    media,
    start,
    reset,
  };
};
