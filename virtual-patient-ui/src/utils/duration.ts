export const formatPlaybackTime = (seconds: number): string => {
  const elapsed = Math.max(0, Math.floor(seconds));
  return `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;
};

export const formatDuration = (durationInSeconds: number | null): string => {
  if (durationInSeconds == null || !Number.isFinite(durationInSeconds)) return '—';

  const totalSeconds = Math.max(0, Math.floor(durationInSeconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const parts: string[] = [];

  if (hours) parts.push(`${hours}h`);
  if (minutes) parts.push(`${minutes}m`);
  if (seconds || !parts.length) parts.push(`${seconds}s`);

  return parts.join(' ');
};
