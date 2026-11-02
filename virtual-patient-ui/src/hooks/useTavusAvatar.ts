import {useCallback, useEffect, useRef, useState} from 'react';
import Daily, {DailyCall, DailyParticipant} from '@daily-co/daily-js';
import {endAvatarSession, startAvatarSession} from '../services/avatar';
import {ECHO_SAMPLE_RATE, encodeEchoAudio} from '../services/avatar/echoAudio';

export type TavusAvatarStatus = 'idle' | 'connecting' | 'ready' | 'failed';

type SpeakWaiter = {resolve: () => void; started: boolean; timer: number};

const START_TIMEOUT_MS = 8000;
const END_GRACE_MS = 4000;

const trackStream = (track: MediaStreamTrack | undefined): MediaStream | null =>
  track ? new MediaStream([track]) : null;

// Connects to a private Tavus (Daily) room that renders Azure-synthesized audio
// as a lip-synced avatar. Any failure leaves the static avatar fallback active.
export const useTavusAvatar = (interviewId: number | null, enabled: boolean) => {
  const [status, setStatus] = useState<TavusAvatarStatus>('idle');
  const [videoStream, setVideoStream] = useState<MediaStream | null>(null);
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const callRef = useRef<DailyCall | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const waiterRef = useRef<SpeakWaiter | null>(null);

  const settleWaiter = useCallback(() => {
    const waiter = waiterRef.current;
    if (!waiter) return;
    window.clearTimeout(waiter.timer);
    waiterRef.current = null;
    waiter.resolve();
  }, []);

  useEffect(() => {
    if (!enabled || interviewId === null) return undefined;
    let cancelled = false;
    let call: DailyCall | null = null;

    const refreshTracks = () => {
      const participants = (call?.participants() ?? {}) as Record<string, DailyParticipant>;
      const remote = Object.values(participants).find((participant) => !participant.local);
      setVideoStream(trackStream(remote?.tracks?.video?.persistentTrack));
      setAudioStream(trackStream(remote?.tracks?.audio?.persistentTrack));
    };

    const connect = async () => {
      setStatus('connecting');
      try {
        const session = await startAvatarSession(interviewId);
        if (cancelled) {
          void endAvatarSession(interviewId);
          return;
        }
        conversationIdRef.current = session.conversationId;
        call = Daily.createCallObject({
          subscribeToTracksAutomatically: true,
          startVideoOff: true,
          startAudioOff: true,
        });
        callRef.current = call;
        call.on('track-started', refreshTracks);
        call.on('track-stopped', refreshTracks);
        call.on('participant-updated', refreshTracks);
        call.on('left-meeting', () => setStatus('failed'));
        call.on('error', () => setStatus('failed'));
        call.on('app-message', (event) => {
          const data = event?.data as {event_type?: string; properties?: {role?: string}} | undefined;
          if (data?.properties?.role === 'user') return;
          const waiter = waiterRef.current;
          if (!waiter) return;
          if (data?.event_type === 'conversation.replica.started_speaking') waiter.started = true;
          if (data?.event_type === 'conversation.replica.stopped_speaking' && waiter.started) settleWaiter();
        });
        await call.join({url: session.conversationUrl, token: session.meetingToken ?? undefined});
        if (cancelled) return;
        refreshTracks();
        setStatus('ready');
      } catch {
        if (!cancelled) setStatus('failed');
        void endAvatarSession(interviewId);
      }
    };

    void connect();

    const onPageHide = () => void endAvatarSession(interviewId, true);
    window.addEventListener('pagehide', onPageHide);

    return () => {
      cancelled = true;
      window.removeEventListener('pagehide', onPageHide);
      settleWaiter();
      if (call) {
        void call.leave().finally(() => call?.destroy());
        void endAvatarSession(interviewId);
      }
      callRef.current = null;
      conversationIdRef.current = null;
      setVideoStream(null);
      setAudioStream(null);
      setStatus('idle');
    };
  }, [enabled, interviewId, settleWaiter]);

  const send = useCallback((eventType: string, properties?: Record<string, unknown>) => {
    const call = callRef.current;
    const conversationId = conversationIdRef.current;
    if (!call || !conversationId) throw new Error('Avatar is not connected');
    call.sendAppMessage(
      {
        message_type: 'conversation',
        event_type: eventType,
        conversation_id: conversationId,
        ...(properties ? {properties} : {}),
      },
      '*',
    );
  }, []);

  // Resolves once the avatar finishes speaking. Rejects before any audio is
  // sent so callers can fall back to local playback.
  const speak = useCallback(
    async (audio: Blob): Promise<void> => {
      const {chunks, durationMs} = await encodeEchoAudio(audio);
      settleWaiter();
      const inferenceId = `turn-${Date.now()}`;
      const finished = new Promise<void>((resolve) => {
        const timer = window.setTimeout(settleWaiter, durationMs + START_TIMEOUT_MS + END_GRACE_MS);
        waiterRef.current = {resolve, started: false, timer};
      });
      chunks.forEach((chunk, index) =>
        send('conversation.echo', {
          modality: 'audio',
          audio: chunk,
          sample_rate: ECHO_SAMPLE_RATE,
          inference_id: inferenceId,
          done: index === chunks.length - 1,
        }),
      );
      await finished;
    },
    [send, settleWaiter],
  );

  const interrupt = useCallback(() => {
    settleWaiter();
    if (status !== 'ready') return;
    try {
      send('conversation.interrupt');
    } catch {
      // The room may already be closing.
    }
  }, [send, settleWaiter, status]);

  return {status, videoStream, audioStream, speak, interrupt};
};
