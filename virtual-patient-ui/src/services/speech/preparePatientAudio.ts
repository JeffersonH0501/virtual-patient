// iPad can report a desktop user agent while retaining iOS media restrictions.
export const usesIOSAudio = () => /iPad|iPhone|iPod/.test(navigator.userAgent)
  || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);

export const preparePatientAudio = () => {
  if (!usesIOSAudio()) return null;
  const audio = new Audio();
  // Play a short silent WAV directly in the acceptance gesture. WebKit grants playback per element.
  audio.src = 'data:audio/wav;base64,UklGRnQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YVAAAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA==';
  void audio.play().catch(() => undefined);
  return audio;
};
