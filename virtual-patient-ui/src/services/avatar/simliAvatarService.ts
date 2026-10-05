import {getAuthHeaders} from '../auth/authHeaders';
import {API_URL} from '../../utils/request';

export type IceServerConfig = {
  urls: string | string[];
  username?: string;
  credential?: string;
};

export type SimliSessionResponse = {
  sessionToken: string;
  iceServers: IceServerConfig[];
  faceId: string;
  maxSessionLength: number;
  maxIdleTime: number;
  enabled: boolean;
};

export type AvatarStatusResponse = {
  enabled: boolean;
  provider: string;
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

export const getSimliAvatarStatus = async (
  interviewId: number,
): Promise<AvatarStatusResponse> => {
  const response = await fetch(
    `${API_URL}/medical-interviews/${interviewId}/avatar/status`,
    {
      method: 'GET',
      headers: {
        accept: 'application/json',
        ...getAuthHeaders(),
      },
    },
  );

  if (!response.ok) {
    return {enabled: false, provider: 'simli'};
  }

  const data = await response.json();
  return {
    enabled: Boolean(data.enabled),
    provider: data.provider || 'simli',
  };
};

export const startSimliAvatarSession = async (
  interviewId: number,
  characterOverride?: string,
): Promise<SimliSessionResponse> => {
  const response = await fetch(
    `${API_URL}/medical-interviews/${interviewId}/avatar/session`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        accept: 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify({
        character_override: characterOverride,
      }),
    },
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const detail =
      errorData && typeof errorData.detail === 'string'
        ? errorData.detail
        : 'Failed to negotiate Simli avatar session';
    throw new Error(detail);
  }

  const data = await response.json();
  return {
    sessionToken: data.session_token,
    iceServers: data.ice_servers || [],
    faceId: data.face_id,
    maxSessionLength: data.max_session_length,
    maxIdleTime: data.max_idle_time,
    enabled: Boolean(data.enabled),
  };
};

export const sendSimliAvatarTelemetry = async (
  interviewId: number,
  telemetry: TurnTelemetryPayload,
): Promise<void> => {
  try {
    await fetch(`${API_URL}/medical-interviews/${interviewId}/avatar/telemetry`, {
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
    // Non-blocking telemetry reporting
  }
};
