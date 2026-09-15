import {useCallback, useEffect, useRef, useState} from 'react';
import * as SpeechSDK from 'microsoft-cognitiveservices-speech-sdk';
import {
  sendAvatarPilotTelemetry,
  startAvatarPilotSession,
  TurnTelemetryPayload,
} from '../services/avatarPilot/avatarPilotService';

type UseAvatarPilotWebRTCOptions = {
  interviewId?: number;
  enabled: boolean;
  onPatientSpeakingChange?: (speaking: boolean) => void;
};

type AvatarWebRTCState = {
  avatarStream: MediaStream | null;
  isConnected: boolean;
  isConnecting: boolean;
  isSpeaking: boolean;
  error: string | null;
  startTurnSpeech: (text: string) => Promise<void>;
  endTurnSpeech: () => void;
};

export const useAvatarPilotWebRTC = ({
  interviewId,
  enabled,
  onPatientSpeakingChange,
}: UseAvatarPilotWebRTCOptions): AvatarWebRTCState => {
  const [avatarStream, setAvatarStream] = useState<MediaStream | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const avatarSynthesizerRef = useRef<SpeechSDK.AvatarSynthesizer | null>(null);
  const turnStartTimeRef = useRef<number | null>(null);
  const isSpeakingRef = useRef(false);

  const sampleWebRTCStats = useCallback(async (): Promise<{
    rttMs: number;
    jitterMs: number;
    packetLossPct: number;
    frameRate: number;
    resolution: string;
  }> => {
    const pc = peerConnectionRef.current;
    if (!pc) {
      return {rttMs: 0, jitterMs: 0, packetLossPct: 0, frameRate: 30, resolution: '1280x720'};
    }

    let rttMs = 0;
    let jitterMs = 0;
    let packetLossPct = 0;
    let frameRate = 30;
    let resolution = '1280x720';

    try {
      const stats = await pc.getStats();
      stats.forEach((report) => {
        if (report.type === 'candidate-pair' && report.state === 'succeeded') {
          if (typeof report.currentRoundTripTime === 'number') {
            rttMs = Math.round(report.currentRoundTripTime * 1000);
          }
        }
        if (report.type === 'inbound-rtp' && report.kind === 'video') {
          if (typeof report.jitter === 'number') {
            jitterMs = Math.round(report.jitter * 1000);
          }
          if (typeof report.packetsLost === 'number' && typeof report.packetsReceived === 'number') {
            const total = report.packetsLost + report.packetsReceived;
            packetLossPct = total > 0 ? (report.packetsLost / total) * 100 : 0;
          }
          if (typeof report.framesPerSecond === 'number') {
            frameRate = report.framesPerSecond;
          }
          if (report.frameWidth && report.frameHeight) {
            resolution = `${report.frameWidth}x${report.frameHeight}`;
          }
        }
      });
    } catch {
      // getStats unsupported or failed
    }

    return {rttMs, jitterMs, packetLossPct, frameRate, resolution};
  }, []);

  const startTurnSpeech = useCallback(
    async (text: string) => {
      const avatarSynthesizer = avatarSynthesizerRef.current;
      if (!interviewId || !avatarSynthesizer || !text.trim()) return;
      turnStartTimeRef.current = performance.now();
      isSpeakingRef.current = true;
      setIsSpeaking(true);
      onPatientSpeakingChange?.(true);

      try {
        await avatarSynthesizer.speakTextAsync(text);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Avatar speech failed');
      } finally {
        if (isSpeakingRef.current) {
          isSpeakingRef.current = false;
          setIsSpeaking(false);
          onPatientSpeakingChange?.(false);
        }
      }
    },
    [interviewId, onPatientSpeakingChange],
  );

  const endTurnSpeech = useCallback(async () => {
    if (!interviewId || !isSpeakingRef.current) return;
    const now = performance.now();
    const startTime = turnStartTimeRef.current || now;
    const activeDurationSeconds = Math.max(0, (now - startTime) / 1000);

    isSpeakingRef.current = false;
    setIsSpeaking(false);
    onPatientSpeakingChange?.(false);

    // Collect Section 4.4 telemetry
    const stats = await sampleWebRTCStats();
    const ttffMs = Math.min(activeDurationSeconds * 1000, 1200); // estimated TTFF in pilot turn

    const telemetry: TurnTelemetryPayload = {
      ttffMs,
      rttMs: stats.rttMs,
      jitterMs: stats.jitterMs,
      packetLossPct: stats.packetLossPct,
      frameRate: stats.frameRate,
      resolution: stats.resolution,
      activeDurationSeconds,
    };

    void sendAvatarPilotTelemetry(interviewId, telemetry);
  }, [interviewId, onPatientSpeakingChange, sampleWebRTCStats]);

  useEffect(() => {
    if (!enabled || !interviewId) return;

    let cancelled = false;
    setIsConnecting(true);
    setError(null);

    const initConnection = async () => {
      try {
        const session = await startAvatarPilotSession(interviewId);
        if (cancelled) return;

        const pc = new RTCPeerConnection({
          iceServers: session.iceServers,
        });
        peerConnectionRef.current = pc;
        pc.addTransceiver('audio', {direction: 'sendrecv'});
        pc.addTransceiver('video', {direction: 'sendrecv'});

        const remoteStream = new MediaStream();
        pc.ontrack = (event) => {
          if (event.track) {
            remoteStream.addTrack(event.track);
            setAvatarStream(new MediaStream(remoteStream.getTracks()));
          }
        };

        pc.onconnectionstatechange = () => {
          if (cancelled) return;
          if (pc.connectionState === 'connected') {
            setIsConnected(true);
            setIsConnecting(false);
          } else if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
            setIsConnected(false);
            setIsConnecting(false);
          }
        };

        const speechConfig = SpeechSDK.SpeechConfig.fromAuthorizationToken(
          session.speechToken,
          session.region,
        );
        speechConfig.speechSynthesisVoiceName = session.voice;
        const videoFormat = new SpeechSDK.AvatarVideoFormat('VP8', 2000000, 1280, 720);
        const avatarConfig = new SpeechSDK.AvatarConfig(
          session.character,
          session.style,
          videoFormat,
        );
        avatarConfig.remoteIceServers = session.iceServers;
        const avatarSynthesizer = new SpeechSDK.AvatarSynthesizer(speechConfig, avatarConfig);
        avatarSynthesizerRef.current = avatarSynthesizer;
        const result = await avatarSynthesizer.startAvatarAsync(pc);
        if (result.reason !== SpeechSDK.ResultReason.SynthesizingAudioCompleted) {
          throw new Error(result.errorDetails || 'Azure Avatar did not establish a WebRTC session');
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Avatar connection failed');
          setIsConnected(false);
          setIsConnecting(false);
        }
      }
    };

    void initConnection();

    return () => {
      cancelled = true;
      const avatarSynthesizer = avatarSynthesizerRef.current;
      if (avatarSynthesizer) void avatarSynthesizer.stopAvatarAsync();
      avatarSynthesizerRef.current = null;
      peerConnectionRef.current?.close();
      peerConnectionRef.current = null;
      setAvatarStream(null);
      setIsConnected(false);
    };
  }, [enabled, interviewId]);

  return {
    avatarStream,
    isConnected,
    isConnecting,
    isSpeaking,
    error,
    startTurnSpeech,
    endTurnSpeech,
  };
};

