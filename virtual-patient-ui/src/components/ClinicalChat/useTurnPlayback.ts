import {useCallback, useEffect, useRef, useState} from 'react';
import type {InterviewRecap} from '../../types/recording';

/**
 * Per-turn recap playback. Each student turn is its own standalone video clip
 * placed on the common session clock by ``sessionClockMs``; the player drives a
 * single timeline from the active clip. Patient turns are text-to-speech and
 * carry no captured media, so they appear as gaps between student clips.
 */
export const useTurnPlayback = (recap: InterviewRecap, seekRequest?: {turnId: string; requestId: number} | null) => {
  const clips = (recap.turnMedia ?? []).flatMap((item) =>
    item.durationMs == null || !item.studentVideoSource ? [] : [{...item, durationMs: item.durationMs, studentVideoSource: item.studentVideoSource}]);
  const [time, setTime] = useState(0);
  const [phase, setPhase] = useState<'paused' | 'buffering' | 'playing' | 'error'>('paused');
  const playing = phase === 'playing' || phase === 'buffering';
  const error = phase === 'error';
  const setPlaying = (value: boolean) => setPhase((current) => value ? 'playing' : current === 'error' ? 'error' : 'paused');
  const setError = (value: boolean) => setPhase((current) => value ? 'error' : current === 'error' ? 'paused' : current);
  const [volume, setVolume] = useState(1);
  const [poster, setPoster] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const waiting = useRef(false);
  const playingRef = useRef(playing);
  const playbackGeneration = useRef(0);
  playingRef.current = playing;
  const duration = (recap.durationMs ?? 0) / 1000;
  const clip = clips.find((item) => time * 1000 >= item.sessionClockMs && time * 1000 < item.sessionClockMs + item.durationMs)
    ?? clips[clips.length - 1];
  const local = Math.max(0, time * 1000 - (clip?.sessionClockMs ?? 0));
  const applied = useRef<number | null>(null);

  const seek = useCallback((seconds: number) => {
    playbackGeneration.current += 1;
    const picture = video.current;
    if (picture && picture.readyState >= 2 && picture.videoWidth && picture.videoHeight) {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = picture.videoWidth; canvas.height = picture.videoHeight;
        canvas.getContext('2d')?.drawImage(picture, 0, 0);
        setPoster(canvas.toDataURL());
      } catch {
        setPoster(null);
      }
    }
    video.current?.pause();
    waiting.current = false;
    setTime(Math.max(0, Math.min(duration, seconds))); setError(false);
  }, [duration]);

  const playMedia = useCallback((element: HTMLMediaElement) => {
    const generation = playbackGeneration.current;
    void element.play().catch((playError: unknown) => {
      if (generation !== playbackGeneration.current) return;
      if (playError instanceof DOMException && playError.name === 'AbortError') return;
      if (playingRef.current) {
        setError(true); setPlaying(false);
      }
    });
  }, []);

  useEffect(() => {
    if (!seekRequest || applied.current === seekRequest.requestId) return;
    const turn = recap.turns.find((item) => item.turnId === seekRequest.turnId);
    if (turn?.startMs != null) seek(turn.startMs / 1000);
    applied.current = seekRequest.requestId;
  }, [seekRequest, recap.turns, seek]);

  useEffect(() => {
    // A position with no student clip is a patient (text-to-speech) gap: advance
    // to the next clip's start so a gap never stalls the recap.
    if (playing && !clip) {
      setPlaying(false);
      return;
    }
    if (playing && clip && time * 1000 >= clip.sessionClockMs + clip.durationMs) {
      const next = clips.find((item) => item.sessionClockMs >= clip.sessionClockMs + clip.durationMs);
      if (next) seek(next.sessionClockMs / 1000);
      else setPlaying(false);
    }
  }, [playing, clip, time, clips, seek]);

  useEffect(() => {
    if (!playing || !clip?.studentVideoSource) {
      video.current?.pause(); return;
    }
    let frame = 0;
    const tick = () => {
      const media = video.current;
      if (media) {
        if (media.ended) {
          const end = Math.min(duration, (clip.sessionClockMs + clip.durationMs) / 1000);
          setTime(end);
          if (end >= duration) setPlaying(false);
        } else if (!waiting.current && media.readyState >= 2 && !media.seeking && !media.paused) {
          setTime(Math.min(duration, (clip.sessionClockMs + clip.durationMs) / 1000, clip.sessionClockMs / 1000 + media.currentTime));
        }
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, duration, clip]);

  useEffect(() => {
    const element = video.current;
    if (!element || !clip) return;
    if (playing && element.error) {
      setError(true); setPlaying(false); return;
    }
    const position = local / 1000;
    if (Math.abs(element.currentTime - position) > .15) element.currentTime = position;
    element.volume = volume;
    element.muted = false;
    if (waiting.current) {
      element.pause(); return;
    }
    if (playing && element.readyState >= 2 && element.paused) {
      playMedia(element);
    }
  }, [clip, local, playing, volume, playMedia]);

  useEffect(() => {
    waiting.current = false;
  }, [clip?.turnMediaId]);

  useEffect(() => () => {
    playingRef.current = false;
    playbackGeneration.current += 1;
  }, []);

  const togglePlayback = () => {
    if (!playing) {
      if (time >= duration) {
        seek(0); setPlaying(true); return;
      }
      if (video.current?.error) video.current.load();
      setError(false);
      playingRef.current = true;
      if (video.current && !waiting.current) playMedia(video.current);
    }
    setPlaying(!playing);
  };

  const videoEvents = (active: boolean) => ({
    onWaiting: () => {
      if (active) {
        waiting.current = true;
        setPhase((current) => current === 'playing' ? 'buffering' : current);
      }
    },
    onCanPlay: () => {
      if (active) {
        waiting.current = false;
        setPhase((current) => current === 'buffering' ? 'playing' : current);
      }
    },
    onSeeked: () => {
      if (active) {
        setPoster(null); waiting.current = false;
      }
    },
    onLoadedData: (event: React.SyntheticEvent<HTMLVideoElement>) => {
      if (active) {
        event.currentTarget.currentTime = local / 1000; waiting.current = false;
      }
    },
    onError: () => {
      if (active && playingRef.current) {
        setError(true); setPlaying(false);
      }
    },
  });

  const activeId = clip?.messageId ?? null;
  return {togglePlayback, clip, time, duration, playing, patientSpeaking: false, volume, setVolume, error, poster,
    video, patientActive: false, activeId, seek, videoEvents};
};
