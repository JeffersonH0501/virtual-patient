import {useEffect, useLayoutEffect, useRef} from 'react';
import {useAppMotion} from './Motion/hooks';

const WAVE_HISTORY_SIZE = 80;
const WAVE_SAMPLE_MS = 100;

export const VoiceWave = ({level, active, speaker}: {
  level: number;
  active: boolean;
  speaker: 'student' | 'patient';
}) => {
  const {reduced} = useAppMotion();
  const trackRef = useRef<HTMLDivElement>(null);
  const levelRef = useRef(level);
  const samplesRef = useRef(Array<number>(WAVE_HISTORY_SIZE).fill(0));
  useLayoutEffect(() => {
    levelRef.current = Number.isFinite(level) ? Math.max(0, Math.min(1, level)) : 0;
  }, [level]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track || !active) return;
    const styles = getComputedStyle(track);
    const barWidth = parseFloat(styles.getPropertyValue('--wave-bar-width'));
    const barGap = parseFloat(styles.getPropertyValue('--wave-bar-gap'));
    if (!Number.isFinite(barWidth + barGap)) return;
    let pixelRatio = 0;
    let step = 0;
    let lastSample = performance.now();
    let frame: number;
    const draw = (now: number) => {
      const ratio = window.devicePixelRatio || 1;
      if (pixelRatio !== ratio) {
        pixelRatio = ratio;
        const width = Math.max(1, Math.round(barWidth * ratio)) / ratio;
        const gap = Math.max(1, Math.round(barGap * ratio)) / ratio;
        step = width + gap;
        track.style.setProperty('--wave-bar-width', `${width}px`);
        track.style.setProperty('--wave-bar-gap', `${gap}px`);
      }
      const elapsed = now - lastSample;
      const count = Math.min(WAVE_HISTORY_SIZE, Math.floor(elapsed / WAVE_SAMPLE_MS));
      if (count > 0) {
        samplesRef.current = [
          ...samplesRef.current.slice(count),
          ...Array<number>(count).fill(levelRef.current),
        ];
        lastSample = now - elapsed % WAVE_SAMPLE_MS;
        Array.from(track.children).forEach((bar, index) => {
          (bar as HTMLElement).style.setProperty('--wave-level', String(samplesRef.current[index]));
        });
      }
      // Move and advance history on one clock, aligned to physical pixels.
      const offset = reduced ? step : (now - lastSample) / WAVE_SAMPLE_MS * step;
      track.style.transform = `translateX(${-Math.round(offset * ratio) / ratio}px)`;
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      track.style.removeProperty('--wave-bar-width');
      track.style.removeProperty('--wave-bar-gap');
    };
  }, [active, reduced]);

  return (
    <div className="voice-wave" data-speaker={speaker} aria-hidden="true">
      <div className="voice-wave-track" ref={trackRef}>
        {Array.from({length: WAVE_HISTORY_SIZE}, (_, index) => <span key={index} />)}
      </div>
    </div>
  );
};
