import {getAuthHeaders} from '../auth/authHeaders';
import {API_URL} from '../../utils/request';

export type AvatarSessionResponse = {
  speechToken: string;
  iceServers: {
    urls: string | string[];
    username?: string;
    credential?: string;
  }[];
  character: string;
  voice: string;
  style: string;
  region: string;
};

export type TurnTelemetryPayload = {
  ttffMs: number;
  rttMs?: number;
  jitterMs?: number;
  packetLossPct?: number;
  frameRate?: number;
  resolution?: string;
  activeDurationSeconds?: number;
};

export const startAvatarPilotSession = async (
  interviewId: number,
  characterOverride?: string,
): Promise<AvatarSessionResponse> => {
  const response = await fetch(`${API_URL}/medical-interviews/${interviewId}/avatar-pilot/session`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({
      character_override: characterOverride,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to initialize avatar session');
  }

  const data = await response.json();
  return {
    speechToken: data.speech_token,
    iceServers: data.ice_servers || [],
    character: data.character,
    voice: data.voice,
    style: data.style,
    region: data.region,
  };
};

export const sendAvatarPilotTelemetry = async (
  interviewId: number,
  telemetry: TurnTelemetryPayload,
): Promise<void> => {
  try {
    await fetch(`${API_URL}/medical-interviews/${interviewId}/avatar-pilot/telemetry`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify({
        ttff_ms: telemetry.ttffMs,
        rtt_ms: telemetry.rttMs || 0.0,
        jitter_ms: telemetry.jitterMs || 0.0,
        packet_loss_pct: telemetry.packetLossPct || 0.0,
        frame_rate: telemetry.frameRate || 30.0,
        resolution: telemetry.resolution || '1280x720',
        active_duration_seconds: telemetry.activeDurationSeconds || 0.0,
      }),
    });
  } catch {
    // Non-blocking telemetry
  }
};

export const getAvatarPilotTelemetryReport = async (
  interviewId: number,
): Promise<Record<string, unknown>> => {
  const response = await fetch(
    `${API_URL}/medical-interviews/${interviewId}/avatar-pilot/telemetry-report`,
    {
      headers: {
        accept: 'application/json',
        ...getAuthHeaders(),
      },
    },
  );

  if (!response.ok) {
    throw new Error('Failed to retrieve telemetry report');
  }

  return response.json();
};

