/**
 * Patient TTS arrives at about -21 LUFS, quiet at full system volume. The same +6 dB boost is
 * applied live and on replay so both sound alike; the limiter keeps boosted peaks from clipping.
 */
export const PATIENT_VOICE_GAIN = 2;

export const connectPatientVoice = (context: AudioContext, source: AudioNode, output: AudioNode = context.destination) => {
  const gain = context.createGain();
  gain.gain.value = PATIENT_VOICE_GAIN;
  const limiter = context.createDynamicsCompressor();
  limiter.threshold.value = -3;
  limiter.knee.value = 0;
  limiter.ratio.value = 20;
  limiter.attack.value = 0.002;
  limiter.release.value = 0.1;
  source.connect(gain);
  gain.connect(limiter);
  limiter.connect(output);
  return () => {
    source.disconnect(gain);
    gain.disconnect();
    limiter.disconnect();
  };
};
