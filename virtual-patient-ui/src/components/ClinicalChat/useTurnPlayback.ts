import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import type {InterviewRecap} from '../../types/recording';

type SeekRequest = {turnId: string; requestId: number} | null;

type TimelineClip = {startMs: number; durationMs: number; messageId: number | null; speaker?: 'student' | 'patient'; voiceStartMs: number | null; voiceEndMs?: number | null};

const timeline = (recap: InterviewRecap): TimelineClip[] => (recap.turnMedia ?? []).flatMap((item) => {
  if (item.durationMs == null) return [];
  const {playbackStartMs: start, playbackEndMs: end} = item.metadata ?? {};
  return [{startMs: item.sessionClockMs, durationMs: item.durationMs, messageId: item.messageId ?? item.metadata?.messageId ?? null,
    speaker: item.metadata?.speaker, voiceStartMs: start != null && end != null && end > start ? start : null,
    voiceEndMs: start != null && end != null && end > start ? end : null}];
}).sort((a, b) => a.startMs - b.startMs);

/**
 * Message to highlight at `ms`. While the patient is still preparing a spoken reply, and during idle
 * time or gaps, the previous turn stays highlighted; a reply without audio is highlighted throughout.
 */
export const highlightedMessage = (clips: TimelineClip[], ms: number): number | null => {
  let active: TimelineClip | undefined;
  for (const clip of clips) if (clip.startMs <= ms) active = clip;
  const covered = active && ms < active.startMs + active.durationMs;
  const waiting = covered && active!.speaker === 'patient' && active!.voiceStartMs != null && ms - active!.startMs < active!.voiceStartMs;
  if (covered && active!.messageId != null && !waiting) return active!.messageId;
  for (let index = clips.length - 1; index >= 0; index--) {
    const clip = clips[index];
    if (clip !== (covered ? active : undefined) && clip.startMs <= ms && clip.messageId != null) return clip.messageId;
  }
  return null;
};

/** Whether the patient's recorded voice is playing at `ms`. */
export const patientSpeakingAt = (clips: TimelineClip[], ms: number) => clips.some((clip) =>
  clip.speaker === 'patient' && clip.voiceStartMs != null && clip.voiceEndMs != null &&
  ms >= clip.startMs + clip.voiceStartMs && ms < clip.startMs + clip.voiceEndMs);

/** Controls for the continuous replay preview: one native video, nothing to synchronize. */
export const useTurnPlayback = (recap: InterviewRecap, seekRequest?: SeekRequest) => {
  const video = useRef<HTMLVideoElement | null>(null);
  const [time, setTime] = useState(0);
  const [mediaDuration, setMediaDuration] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [volume, setVolumeState] = useState(1);
  const [error, setError] = useState(false);
  const appliedRequest = useRef<number | null>(null);
  const duration = mediaDuration ?? (recap.durationMs ?? 0) / 1000;
  const clips = useMemo(() => timeline(recap), [recap]);

  const seek = useCallback((seconds: number) => {
    const target = Math.max(0, Math.min(seconds, video.current?.duration || seconds));
    if (video.current) video.current.currentTime = target;
    setTime(target);
  }, []);

  useEffect(() => {
    if (!seekRequest || appliedRequest.current === seekRequest.requestId) return;
    const turn = recap.turns.find((item) => item.turnId === seekRequest.turnId);
    if (turn?.startMs != null) seek(turn.startMs / 1000);
    appliedRequest.current = seekRequest.requestId;
  }, [seekRequest, recap.turns, seek]);

  const togglePlayback = () => {
    const element = video.current;
    if (!element) return;
    if (!element.paused) {
      element.pause(); return;
    }
    if (element.ended) element.currentTime = 0;
    setError(false);
    void element.play()?.catch((reason: unknown) => {
      if (!(reason instanceof DOMException && reason.name === 'AbortError')) setError(true);
    });
  };

  const setVolume = (next: number) => {
    setVolumeState(next);
    if (video.current) video.current.volume = next;
  };

  const videoEvents = {
    onTimeUpdate: (event: React.SyntheticEvent<HTMLVideoElement>) => setTime(event.currentTarget.currentTime),
    onLoadedMetadata: (event: React.SyntheticEvent<HTMLVideoElement>) => {
      const element = event.currentTarget;
      element.volume = volume;
      if (Number.isFinite(element.duration)) setMediaDuration(element.duration);
    },
    onPlay: () => setPlaying(true),
    onPause: () => setPlaying(false),
    onEnded: () => setPlaying(false),
    onError: () => {
      setPlaying(false); setError(true);
    },
  };

  return {video, videoEvents, togglePlayback, time, duration, playing, volume, setVolume, error, seek,
    activeId: highlightedMessage(clips, time * 1000), patientSpeaking: playing && patientSpeakingAt(clips, time * 1000)};
};
