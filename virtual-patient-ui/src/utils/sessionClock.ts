export type PauseInterval = {start: number; end: number | null};

/** Map an event timestamp without subtracting pauses that happened later. */
export const sessionElapsedAt = (timestamp: number, origin: number, pauses: PauseInterval[]): number => {
  const paused = pauses.reduce((total, interval) =>
    total + Math.max(0, Math.min(timestamp, interval.end ?? timestamp) - Math.max(origin, interval.start)), 0);
  return Math.max(0, Math.round(timestamp - origin - paused));
};
