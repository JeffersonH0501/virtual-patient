export const selectSupportedMimeType = (candidates: string[]): string | null => {
  if (typeof MediaRecorder === 'undefined') return null;
  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? null;
};

export const selectAudioMimeType = (): string | null => selectSupportedMimeType([
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
]);

export const selectVideoMimeType = (): string | null => selectSupportedMimeType([
  'video/webm;codecs=vp8,opus',
  'video/webm;codecs=vp8',
  'video/webm',
  'video/mp4',
]);
