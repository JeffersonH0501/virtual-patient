import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import type {InterviewRecap} from '../../types/recording';
import {resolveRecordingSource} from '../../services/recordings';
import {getAuthHeaders} from '../../services/auth/authHeaders';

export const useBlockPlayback = (recap: InterviewRecap, seekRequest?: {turnId: string; requestId: number} | null) => {
  const blocks = useMemo(() => (recap.blocks ?? []).flatMap((item) => item.durationMs == null ? [] : [{...item, durationMs: item.durationMs}]), [recap.blocks]);
  const [time, setTime] = useState(0);
  const [phase, setPhase] = useState<'paused' | 'buffering' | 'playing' | 'error'>('paused');
  const playing = phase === 'playing' || phase === 'buffering';
  const error = phase === 'error';
  const setPlaying = (value: boolean) => setPhase((current) => value ? 'playing' : current === 'error' ? 'error' : 'paused');
  const setError = (value: boolean) => setPhase((current) => value ? 'error' : current === 'error' ? 'paused' : current);
  const [patientSpeaking, setPatientSpeaking] = useState(false);
  const [volume, setVolume] = useState(1);
  const [audioUrls, setAudioUrls] = useState<Record<string, string>>({});
  const audioCache = useRef(new Map<string, {controller: AbortController; url?: string}>());
  const [poster, setPoster] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const selectedAudio = useRef<{blockId?: string; source?: string}>({});
  const waiting = useRef({video: false, audio: false});
  const [mediaReady, setMediaReady] = useState(0);
  const playingRef = useRef(playing);
  const playbackGeneration = useRef(0);
  playingRef.current = playing;
  const duration = (recap.durationMs ?? 0) / 1000;
  const block = blocks.find((item) => time * 1000 >= item.offsetMs && time * 1000 < item.offsetMs + item.durationMs) ?? blocks[blocks.length - 1];
  const nextBlock = block ? blocks[blocks.findIndex((item) => item.blockId === block.blockId) + 1] : undefined;
  const local = Math.max(0, time * 1000 - (block?.offsetMs ?? 0));
  const patient = block?.metadata.patientPlayback;
  const student = block?.metadata.studentSpeech;
  const patientActive = Boolean(patient && local >= patient.startMs && local < patient.endMs);
  const activeId = patientActive ? block?.metadata.patientMessageId : block?.metadata.studentMessageId;
  const currentAudioSource = block?.patientAudioSource;
  const nextAudioSource = nextBlock?.patientAudioSource;
  if (selectedAudio.current.blockId !== block?.blockId || !playing) {
    selectedAudio.current = {blockId: block?.blockId,
      source: block?.patientAudioSource ? audioUrls[block.patientAudioSource] || resolveRecordingSource(block.patientAudioSource) || undefined : undefined};
  }
  useEffect(() => {
    const wanted = new Set([currentAudioSource, nextAudioSource].filter((source): source is string => Boolean(source)));
    for (const [source, entry] of audioCache.current) {
      if (wanted.has(source) || (playing && entry.url === selectedAudio.current.source)) continue;
      entry.controller.abort();
      if (entry.url) URL.revokeObjectURL(entry.url);
      audioCache.current.delete(source);
    }
    setAudioUrls((current) => Object.fromEntries(Object.entries(current).filter(([source]) => wanted.has(source))));
    for (const source of wanted) {
      if (audioCache.current.has(source)) continue;
      const controller = new AbortController();
      const entry: {controller: AbortController; url?: string} = {controller};
      audioCache.current.set(source, entry);
      void (async () => {
        try {
          const response = await fetch(resolveRecordingSource(source)!, {headers: getAuthHeaders(), credentials: 'include', signal: controller.signal});
          if (!response.ok) throw new Error('Patient audio request failed');
          const blob = await response.blob();
          if (!blob.size || !blob.type.startsWith('audio/')) throw new Error('Patient audio is invalid');
          if (controller.signal.aborted) return;
          const url = URL.createObjectURL(blob);
          entry.url = url;
          setAudioUrls((current) => ({...current, [source]: url}));
        } catch (loadError) {
          if (!controller.signal.aborted) console.error('Patient audio preload failed', loadError);
        }
      })();
    }
  }, [currentAudioSource, nextAudioSource, playing]);
  useEffect(() => {
    const cache = audioCache.current;
    return () => {
      for (const entry of cache.values()) {
        entry.controller.abort();
        if (entry.url) URL.revokeObjectURL(entry.url);
      }
      cache.clear();
    };
  }, []);
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
    video.current?.pause(); audio.current?.pause();
    waiting.current = {video: false, audio: false};
    setTime(Math.max(0, Math.min(duration, seconds))); setError(false);
  }, [duration]);
  const failPlayback = useCallback((element: HTMLMediaElement) => {
    if (!playingRef.current || (element !== video.current && element !== audio.current)) return;
    setError(true); setPlaying(false);
  }, []);
  const playMedia = useCallback((element: HTMLMediaElement) => {
    const generation = playbackGeneration.current;
    void element.play().catch((playError: unknown) => {
      if (generation !== playbackGeneration.current) return;
      if (playError instanceof DOMException && playError.name === 'AbortError') return;
      failPlayback(element);
    });
  }, [failPlayback]);
  const mediaWaiting = (kind: 'video' | 'audio') => {
    playbackGeneration.current += 1;
    waiting.current[kind] = true;
    setPhase((current) => current === 'playing' ? 'buffering' : current);
    video.current?.pause(); audio.current?.pause();
  };
  const mediaAvailable = (kind: 'video' | 'audio') => {
    waiting.current[kind] = false;
    if (!waiting.current.video && !waiting.current.audio) {
      setPhase((current) => current === 'buffering' ? 'playing' : current);
    }
    setMediaReady((version) => version + 1);
  };
  useEffect(() => {
    waiting.current = {video: false, audio: false};
  }, [block?.blockId]);

  useEffect(() => {
    if (!seekRequest || applied.current === seekRequest.requestId) return;
    const turn = recap.turns.find((item) => item.turnId === seekRequest.turnId);
    if (turn?.startMs != null) seek(turn.startMs / 1000);
    applied.current = seekRequest.requestId;
  }, [seekRequest, recap.turns, seek]);
  useEffect(() => {
    if (playing && block && !block.studentVideoSource && !(patientActive && block.patientAudioSource)) {
      setError(true);
      setPlaying(false);
    }
  }, [playing, block, patientActive]);
  useEffect(() => {
    if (!playing) {
      video.current?.pause(); audio.current?.pause(); return;
    }
    let frame = 0;
    const tick = () => {
      const media = video.current;
      if (block?.studentVideoSource && media) {
        if (media.ended) {
          const end = Math.min(duration, (block.offsetMs + block.durationMs) / 1000);
          const actual = Math.min(end, block.offsetMs / 1000 + media.currentTime);
          const reportedDuration = media.duration;
          if (Number.isFinite(reportedDuration) && reportedDuration > 0 && block.durationMs / 1000 - reportedDuration > .15) {
            setTime(actual);
            setError(true);
            setPlaying(false);
          } else {
            setTime(end);
            if (end >= duration) setPlaying(false);
          }
        } else if (!waiting.current.video && !(patientActive && block.patientAudioSource && waiting.current.audio) && media.readyState >= 2 && !media.seeking && !media.paused) {
          setTime(Math.min(duration, (block.offsetMs + block.durationMs) / 1000, block.offsetMs / 1000 + media.currentTime));
        }
      } else if (block?.patientAudioSource && patient && audio.current) {
        const sound = audio.current;
        if (!waiting.current.audio && sound.readyState >= 2 && !sound.seeking && !sound.paused) {
          setTime(Math.min(duration, (block.offsetMs + patient.endMs) / 1000, (block.offsetMs + patient.startMs) / 1000 + sound.currentTime));
        }
        if (sound.ended) setPlaying(false);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, duration, block, patient, patientActive]);
  useEffect(() => {
    const element = video.current;
    if (!element || !block) return;
    if (playing && element.error) {
      setError(true);
      setPlaying(false);
      return;
    }
    const position = local / 1000;
    if (Math.abs(element.currentTime - position) > .15) element.currentTime = position;
    element.muted = !student || local < student.startMs || local >= student.endMs || patientActive;
    element.volume = volume;
    if (waiting.current.video || (patientActive && block.patientAudioSource && (waiting.current.audio || !audio.current || audio.current.readyState < 2))) {
      element.pause(); audio.current?.pause(); return;
    }
    if (playing && element.readyState >= 2 && element.paused) {
      playMedia(element);
    }
  }, [block, local, playing, volume, patientActive, student, mediaReady, playMedia]);
  useEffect(() => {
    const element = audio.current;
    if (!element) return;
    element.volume = volume;
    if (!patient || !patientActive || !playing || !block?.patientAudioSource) {
      element.pause(); return;
    }
    if (waiting.current.audio || element.readyState < 2 || (block.studentVideoSource && (waiting.current.video || !video.current || video.current.readyState < 2 || video.current.seeking))) {
      element.pause(); video.current?.pause(); return;
    }
    const position = Math.max(0, (local - patient.startMs) / 1000);
    element.muted = false;
    if (Math.abs(element.currentTime - position) > .15) element.currentTime = position;
    if (element.paused) {
      playMedia(element);
    }
  }, [patientActive, patient, local, playing, volume, block, mediaReady, playMedia]);
  useEffect(() => {
    const picture = video.current;
    const sound = audio.current;
    return () => {
      picture?.pause(); sound?.pause();
    };
  }, [block?.blockId]);
  useEffect(() => () => {
    playingRef.current = false;
    playbackGeneration.current += 1;
  }, []);

  const togglePlayback = () => {
        if (!playing) {
          if (time >= duration) {
            seek(0); setPlaying(true); return;
          }
          if (!block?.studentVideoSource && !(patientActive && block?.patientAudioSource)) {
            setError(true); return;
          }
          if (video.current?.error) video.current.load();
          if (audio.current?.error && block.patientAudioSource) audio.current.load();
          setError(false);
          playingRef.current = true;
          if (video.current && !waiting.current.video && (!patientActive || !block.patientAudioSource || (audio.current && audio.current.readyState >= 2 && !waiting.current.audio))) playMedia(video.current);
          if (audio.current) {
            const element = audio.current;
            if (patientActive && element.readyState >= 2 && !waiting.current.audio && (!block.studentVideoSource || (video.current && video.current.readyState >= 2 && !waiting.current.video))) {
              element.currentTime = Math.max(0, (local - patient!.startMs) / 1000);
              playMedia(element);
            } else if (!patientActive && element.src) {
              element.muted = true; void element.play().then(() => {
                if (element.muted) {
                  element.pause(); element.currentTime = 0; element.muted = false;
                }
              }).catch(() => {
                element.muted = false;
              });
            }
          }
        }
        setPlaying(!playing);
      };
  const videoEvents = (active: boolean) => ({
    onWaiting: () => {
      if (active) mediaWaiting('video');
    },
    onPause: (event: React.SyntheticEvent<HTMLVideoElement>) => {
      if (event.currentTarget === video.current) audio.current?.pause();
    },
    onCanPlay: () => {
      if (active) mediaAvailable('video');
    },
    onSeeked: () => {
      if (active) {
        setPoster(null); mediaAvailable('video');
      }
    },
    onLoadedData: (event: React.SyntheticEvent<HTMLVideoElement>) => {
      if (active) {
        event.currentTarget.currentTime = local / 1000; mediaAvailable('video');
      }
    },
    onError: () => {
      if (active && playingRef.current) {
        setError(true); setPlaying(false);
      }
    },
  });
  const audioEvents = {
    onPlaying: () => setPatientSpeaking(!audio.current?.muted),
    onPause: () => setPatientSpeaking(false),
    onEnded: () => setPatientSpeaking(false),
    onCanPlay: () => mediaAvailable('audio'),
    onSeeked: () => mediaAvailable('audio'),
    onWaiting: () => {
      if (patientActive) mediaWaiting('audio');
    },
    onError: () => {
      if (playingRef.current && patientActive && block?.patientAudioSource) {
        setError(true); setPlaying(false);
      }
    },
  };
  return {togglePlayback, block, nextBlock, time, duration, playing, patientSpeaking, volume, setVolume, error, poster,
    video, audio, audioSource: selectedAudio.current.source, patientActive, activeId, seek, videoEvents, audioEvents};
};
