import {useCallback, useEffect, useRef, useState, type RefObject} from 'react';
import {SimliClient} from 'simli-client';
import {
  getSimliAvatarStatus,
  sendSimliAvatarTelemetry,
  startSimliAvatarSession,
} from '../services/avatar/simliAvatarService';

/**
 * Decode an MP3/WAV/AAC audio Blob and downsample to PCM16 16kHz mono Uint8Array.
 * Required by Simli's audio-to-video processing pipeline.
 */
export async function convertBlobToPcm16(audioBlob: Blob): Promise<Uint8Array> {
  const arrayBuffer = await audioBlob.arrayBuffer();
  const AudioCtx =
    window.AudioContext ||
    (window as unknown as {webkitAudioContext: typeof AudioContext})
      .webkitAudioContext;
  const audioContext = new AudioCtx();

  try {
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

    // Resample to 16kHz mono using an OfflineAudioContext
    const TARGET_SAMPLE_RATE = 16000;
    const targetLength = Math.max(
      1,
      Math.ceil(audioBuffer.duration * TARGET_SAMPLE_RATE),
    );
    const offlineCtx = new OfflineAudioContext(1, targetLength, TARGET_SAMPLE_RATE);

    const source = offlineCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(offlineCtx.destination);
    source.start(0);

    const rendered = await offlineCtx.startRendering();
    const float32Samples = rendered.getChannelData(0);

    // Convert Float32 [-1.0, 1.0] to signed Int16 [-32768, 32767]
    const pcm16 = new Int16Array(float32Samples.length);
    for (let i = 0; i < float32Samples.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Samples[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }

    return new Uint8Array(pcm16.buffer);
  } finally {
    await audioContext.close().catch(() => undefined);
  }
}

type UseSimliAvatarOptions = {
  interviewId?: number;
  enabled?: boolean;
  characterOverride?: string;
  onPatientSpeakingChange?: (speaking: boolean) => void;
};

export type SimliAvatarState = {
  avatarStream: MediaStream | null;
  isConnected: boolean;
  isConnecting: boolean;
  isSpeaking: boolean;
  error: string | null;
  videoRef: RefObject<HTMLVideoElement | null>;
  audioRef: RefObject<HTMLAudioElement | null>;
  sendAudioTurn: (audioBlob: Blob) => Promise<void>;
  clearBuffer: () => void;
  close: () => void;
};

const CHUNK_SIZE_BYTES = 6000; // ~187.5ms of 16kHz 16-bit mono audio

export const useSimliAvatar = ({
  interviewId,
  enabled = true,
  characterOverride,
  onPatientSpeakingChange,
}: UseSimliAvatarOptions): SimliAvatarState => {
  const [avatarStream, setAvatarStream] = useState<MediaStream | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const clientRef = useRef<SimliClient | null>(null);
  const isConnectedRef = useRef(false);
  const isConnectingRef = useRef(false);

  // Keep ref up to date
  isConnectedRef.current = isConnected;

  const close = useCallback(() => {
    if (clientRef.current) {
      try {
        void clientRef.current.stop();
      } catch {
        // Ignore shutdown errors
      }
      clientRef.current = null;
    }
    if (audioRef.current) {
      try {
        audioRef.current.pause();
        audioRef.current.srcObject = null;
        audioRef.current.remove();
      } catch {
        // Ignore cleanup errors
      }
      audioRef.current = null;
    }
    setIsConnected(false);
    setIsConnecting(false);
    setAvatarStream(null);
  }, []);

  const clearBuffer = useCallback(() => {
    if (clientRef.current) {
      try {
        clientRef.current.ClearBuffer();
      } catch {
        // Non-fatal
      }
    }
    setIsSpeaking(false);
    onPatientSpeakingChange?.(false);
  }, [onPatientSpeakingChange]);

  const sendAudioTurn = useCallback(
    async (audioBlob: Blob) => {
      if (!clientRef.current || !isConnectedRef.current) return;
      const turnStartTime = performance.now();

      try {
        const pcm16Data = await convertBlobToPcm16(audioBlob);
        if (!clientRef.current || !isConnectedRef.current) return;

        for (
          let offset = 0;
          offset < pcm16Data.length;
          offset += CHUNK_SIZE_BYTES
        ) {
          const chunk = pcm16Data.subarray(
            offset,
            Math.min(offset + CHUNK_SIZE_BYTES, pcm16Data.length),
          );
          clientRef.current.sendAudioData(chunk);
        }

        const ttffMs = Math.round(performance.now() - turnStartTime);
        const activeDurationSeconds =
          pcm16Data.length > 0 ? pcm16Data.length / 32000 : 0;

        if (interviewId) {
          void sendSimliAvatarTelemetry(interviewId, {
            ttffMs,
            frameRate: 30,
            resolution: '1280x720',
            activeDurationSeconds,
          });
        }
      } catch (err) {
        console.warn('Failed to stream audio to Simli avatar:', err);
      }
    },
    [interviewId],
  );

  useEffect(() => {
    if (!enabled || !interviewId || isConnectingRef.current || isConnectedRef.current) {
      return;
    }

    let active = true;
    isConnectingRef.current = true;
    setIsConnecting(true);
    setError(null);

    const initSimli = async () => {
      try {
        const status = await getSimliAvatarStatus(interviewId);
        if (!active) return;
        if (!status.enabled) {
          setIsConnecting(false);
          isConnectingRef.current = false;
          return;
        }

        const session = await startSimliAvatarSession(
          interviewId,
          characterOverride,
        );
        if (!active) return;

        // Ensure video and audio DOM elements exist for Simli anchor
        if (!videoRef.current) {
          const v = document.createElement('video');
          v.playsInline = true;
          v.autoplay = true;
          videoRef.current = v;
        }
        if (!audioRef.current) {
          const a = document.createElement('audio');
          a.autoplay = true;
          a.playsInline = true;
          a.style.display = 'none';
          document.body.appendChild(a);
          audioRef.current = a;
        }

        const client = new SimliClient(
          session.sessionToken,
          videoRef.current,
          audioRef.current,
          session.iceServers,
        );
        clientRef.current = client;

        client.on('start', () => {
          if (!active) return;
          setIsConnected(true);
          setIsConnecting(false);
          isConnectingRef.current = false;
          if (videoRef.current?.srcObject instanceof MediaStream) {
            setAvatarStream(videoRef.current.srcObject);
          }
        });

        client.on('speaking', () => {
          if (!active) return;
          setIsSpeaking(true);
          onPatientSpeakingChange?.(true);
        });

        client.on('silent', () => {
          if (!active) return;
          setIsSpeaking(false);
          onPatientSpeakingChange?.(false);
        });

        client.on('error', (detail: string) => {
          if (!active) return;
          console.warn('Simli client error:', detail);
          setError(detail);
        });

        client.on('startup_error', (detail: string) => {
          if (!active) return;
          console.warn('Simli startup error:', detail);
          setError(detail);
          setIsConnecting(false);
          isConnectingRef.current = false;
        });

        await client.start();
      } catch (err: unknown) {
        if (!active) return;
        const msg = err instanceof Error ? err.message : String(err);
        console.warn('Simli session initialization failed:', msg);
        setError(msg);
        setIsConnecting(false);
        isConnectingRef.current = false;
      }
    };

    void initSimli();

    return () => {
      active = false;
      isConnectingRef.current = false;
      close();
    };
  }, [characterOverride, close, enabled, interviewId, onPatientSpeakingChange]);

  return {
    avatarStream,
    isConnected,
    isConnecting,
    isSpeaking,
    error,
    videoRef,
    audioRef,
    sendAudioTurn,
    clearBuffer,
    close,
  };
};
