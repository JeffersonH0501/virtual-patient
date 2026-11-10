export const calculateDuration = (startTime: string | null, endTime: string | null): number => {
  if (!startTime || !endTime) return 0;
  const start = new Date(startTime);
  const end = new Date(endTime);
  return Math.floor((end.getTime() - start.getTime()) / 1000);
};

