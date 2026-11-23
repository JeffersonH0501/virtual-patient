import {useCallback, useEffect, useRef, useState} from 'react';
import {usesIOSAudio} from '../services/speech/preparePatientAudio';
import {connectPatientVoice, PATIENT_VOICE_GAIN} from '../utils/patientVoice';

/** Route patient TTS through Web Audio where supported and expose its speaking level. */
export const usePatientAudioRoute = () => {
  const [level, setLevel] = useState(0);
  const context = useRef<AudioContext | null>(null);
  const sources = useRef(new WeakMap<HTMLAudioElement, MediaElementAudioSourceNode>());
  const cleanup = useRef<(() => void) | null>(null);

  useEffect(() => () => {
    cleanup.current?.();
    void context.current?.close().catch(() => undefined);
  }, []);

  const resumeAudioGraph = useCallback(async () => {
    // Keep iOS playback on the native player while the interview captures the microphone.
    if (typeof window === 'undefined' || !window.AudioContext || usesIOSAudio()) return;
    context.current ??= new AudioContext();
    if (context.current.state !== 'running') await context.current.resume();
  }, []);

  const routePatientAudio = useCallback((audio: HTMLAudioElement) => {
    const graph = context.current;
    if (graph?.state !== 'running') return false;
    cleanup.current?.();
    const source = sources.current.get(audio) ?? graph.createMediaElementSource(audio);
    sources.current.set(audio, source);
    const analyser = graph.createAnalyser();
    analyser.fftSize = 1024;
    const samples = new Float32Array(analyser.fftSize);
    const disconnectVoice = connectPatientVoice(graph, source, analyser);
    analyser.connect(graph.destination);
    const timer = window.setInterval(() => {
      if (audio.ended) {
        cleanup.current?.(); return;
      }
      // Capture pauses resume the same player, which still needs its audio output connected.
      if (audio.paused) {
        setLevel(0); return;
      }
      analyser.getFloatTimeDomainData(samples);
      const rms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length);
      // Measured after the boost; scaled so the speaking indicator keeps its range.
      setLevel(Math.min(1, rms / (0.16 * PATIENT_VOICE_GAIN)));
    }, 60);
    cleanup.current = () => {
      window.clearInterval(timer);
      disconnectVoice();
      analyser.disconnect();
      cleanup.current = null;
      setLevel(0);
    };
    return true;
  }, []);

  return {patientAudioLevel: level, resumeAudioGraph, routePatientAudio};
};
