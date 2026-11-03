const activeTurns = new Map<number, number>();

export type AvatarTimingStage =
  | 'message-ready'
  | 'tts-server'
  | 'tts-ready'
  | 'pcm-ready'
  | 'echo-sent'
  | 'replica-started'
  | 'replica-finished'
  | 'replica-timeout'
  | 'fallback';

const startMark = 'virtual-patient-avatar:turn-start';
const timingStages: AvatarTimingStage[] = [
  'message-ready',
  'tts-server',
  'tts-ready',
  'pcm-ready',
  'echo-sent',
  'replica-started',
  'replica-finished',
  'replica-timeout',
  'fallback',
];

export const startAvatarTurnTiming = (interviewId: number) => {
  if (!import.meta.env.DEV) return;
  const startedAt = performance.now();
  activeTurns.set(interviewId, startedAt);
  performance.clearMarks(startMark);
  for (const stage of timingStages) {
    performance.clearMarks(`virtual-patient-avatar:${stage}`);
    performance.clearMeasures(`virtual-patient-avatar:turn-to-${stage}`);
    performance.clearMeasures(`virtual-patient-avatar:stage-duration:${stage}`);
  }
  performance.mark(startMark);
};

export const ensureAvatarTurnTiming = (interviewId: number) => {
  if (!activeTurns.has(interviewId)) startAvatarTurnTiming(interviewId);
};

export const recordAvatarTimingStage = (
  interviewId: number,
  stage: AvatarTimingStage,
  stageDurationMs?: number,
) => {
  if (!import.meta.env.DEV) return;
  const startedAt = activeTurns.get(interviewId);
  if (startedAt === undefined) return;

  const endedAt = performance.now();
  const markName = `virtual-patient-avatar:${stage}`;
  performance.mark(markName);
  performance.measure(
    `virtual-patient-avatar:turn-to-${stage}`,
    {start: startedAt, end: endedAt},
  );
  if (stageDurationMs !== undefined) {
    performance.measure(`virtual-patient-avatar:stage-duration:${stage}`, {
      duration: stageDurationMs,
      end: endedAt,
    });
  }
};

export const finishAvatarTurnTiming = (interviewId: number) => {
  activeTurns.delete(interviewId);
};

export const logAvatarConnectionTiming = (stage: string, durationMs: number) => {
  if (!import.meta.env.DEV) return;
  const measureName = `virtual-patient-avatar:connection:${stage}`;
  performance.clearMeasures(measureName);
  performance.measure(measureName, {
    duration: durationMs,
    end: performance.now(),
  });
};
