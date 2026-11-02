// Tavus Echo mode expects base64 PCM 16-bit mono audio. The rate is declared
// in each message; validate the accepted format in the provider proof of concept.
export const ECHO_SAMPLE_RATE = 16000;
const CHUNK_SAMPLES = ECHO_SAMPLE_RATE * 2;

const toBase64 = (samples: Int16Array): string => {
  const bytes = new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength);
  let binary = '';
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  }
  return btoa(binary);
};

export type EchoAudio = {
  chunks: string[];
  durationMs: number;
};

// Decodes an encoded clip (Azure TTS mp3) to mono PCM16 at the echo sample rate.
export const encodeEchoAudio = async (blob: Blob): Promise<EchoAudio> => {
  const context = new AudioContext();
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer());
    const length = Math.max(1, Math.ceil(decoded.duration * ECHO_SAMPLE_RATE));
    const offline = new OfflineAudioContext(1, length, ECHO_SAMPLE_RATE);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const rendered = (await offline.startRendering()).getChannelData(0);

    const pcm = new Int16Array(rendered.length);
    for (let index = 0; index < rendered.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, rendered[index]));
      pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    const chunks: string[] = [];
    for (let offset = 0; offset < pcm.length; offset += CHUNK_SAMPLES) {
      chunks.push(toBase64(pcm.subarray(offset, offset + CHUNK_SAMPLES)));
    }
    return {chunks, durationMs: Math.round(decoded.duration * 1000)};
  } finally {
    void context.close();
  }
};
