/**
 * Format duration in seconds to a human-readable string
 * @param durationInSeconds - Duration in seconds
 * @param minLabel - Label for minutes (e.g., 'min')
 * @returns Formatted duration string
 * 
 * Examples:
 * - 30 seconds -> "0.50 min"
 * - 660 seconds (11 min) -> "11 min"
 * - 5400 seconds (90 min) -> "1h 30min"
 * - 7200 seconds (120 min) -> "2h"
 */
export const formatDuration = (durationInSeconds: number | null, minLabel: string): string => {
  if (!durationInSeconds) return `0 ${minLabel}`;
  
  const days = Math.floor(durationInSeconds / 86400);
  const hours = Math.floor((durationInSeconds % 86400) / 3600);
  const minutes = Math.floor((durationInSeconds % 3600) / 60);
  const remainingSeconds = Math.floor(durationInSeconds % 60);

  // If we have days, only show days
  if (days > 0) {
    return `${days}d`;
  }

  // If we have hours, show hours (round up if there are minutes or seconds)
  if (hours > 0) {
    const hasMinutesOrSeconds = minutes > 0 || remainingSeconds > 0;
    return hasMinutesOrSeconds ? `${hours + 1}h` : `${hours}h`;
  }

  // If we only have minutes, show minutes (round up if there are seconds)
  if (minutes > 0) {
    const hasSeconds = remainingSeconds > 0;
    return hasSeconds ? `${minutes + 1}${minLabel}` : `${minutes}${minLabel}`;
  }

  // If we only have seconds, show seconds
  return `${remainingSeconds}s`;
};

