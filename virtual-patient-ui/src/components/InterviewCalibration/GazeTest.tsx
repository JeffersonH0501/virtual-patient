import {useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {readGeometry} from '../../hooks/useTechnicalCalibration';
import {processGazeTestFrame} from '../../services/interviews/calibration';
import {Button} from '../common/Button';

type Geometry = ReturnType<typeof readGeometry>;
type Props = {stream: MediaStream; attemptId: string; gazeToken: string; cameraToken: string; geometry: Geometry; onRestart: () => void; onExit: () => void};

export const GazeTest = ({stream, attemptId, gazeToken, cameraToken, geometry, onRestart, onExit}: Props) => {
  const {t} = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const areaRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<'inside' | 'outside' | 'indeterminate'>('indeterminate');
  const [changed, setChanged] = useState(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
    const canvas = document.createElement('canvas');
    let stopped = false;
    let timer: number | undefined;
    let stale: number | undefined;
    let deadline: number | undefined;
    let controller: AbortController | undefined;
    const geometryMatches = () => {
      const current = readGeometry(stream);
      return (Object.keys(current) as (keyof Geometry)[]).every((key) => current[key] === geometry[key]);
    };
    const invalidate = () => {
      stopped = true;
      controller?.abort();
      setState('indeterminate');
      setChanged(true);
    };
    const tick = async () => {
      if (stopped) return;
      if (!geometryMatches() || !stream.active) {
        invalidate(); return;
      }
      const track = stream.getVideoTracks()[0];
      if (track?.readyState === 'live' && !track.muted && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth && video.videoHeight) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext('2d');
        if (context) {
          context.drawImage(video, 0, 0);
          const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', .65));
          if (blob && !stopped) {
            controller = new AbortController();
            const startedAt = performance.now();
            stale = window.setTimeout(() => setState('indeterminate'), 3000);
            deadline = window.setTimeout(() => controller?.abort(), 15000);
            try {
              const rect = areaRef.current?.getBoundingClientRect();
              if (!rect || rect.width <= 0 || rect.height <= 0) throw new Error('Interaction area unavailable');
              const interactionArea = {timestampMs: 0, xNormalized: Math.max(0, rect.x) / innerWidth,
                yNormalized: Math.max(0, rect.y) / innerHeight,
                widthNormalized: (Math.min(innerWidth, rect.right) - Math.max(0, rect.x)) / innerWidth,
                heightNormalized: (Math.min(innerHeight, rect.bottom) - Math.max(0, rect.y)) / innerHeight};
              const next = await processGazeTestFrame(blob, attemptId, {gaze: gazeToken, camera: cameraToken}, geometry, interactionArea, controller.signal);
              if (!stopped) setState(performance.now() - startedAt <= 3000 ? next : 'indeterminate');
            } catch (error) {
              if (!stopped) {
                setState('indeterminate');
                if (error instanceof Error && 'status' in error && [409, 410, 422].includes(Number(error.status))) invalidate();
              }
            } finally {
              clearTimeout(stale);
              clearTimeout(deadline);
            }
          } else if (!stopped) setState('indeterminate');
        } else setState('indeterminate');
      } else setState('indeterminate');
      if (!stopped) timer = window.setTimeout(() => void tick(), 800);
    };
    window.addEventListener('resize', invalidate);
    document.addEventListener('visibilitychange', invalidate);
    void tick();
    return () => {
      stopped = true;
      controller?.abort();
      clearTimeout(timer);
      clearTimeout(stale);
      clearTimeout(deadline);
      window.removeEventListener('resize', invalidate);
      document.removeEventListener('visibilitychange', invalidate);
      video.srcObject = null;
    };
  }, [stream, attemptId, gazeToken, cameraToken, geometry]);

  const color = state === 'inside' ? '#15803d' : state === 'outside' ? '#b91c1c' : '#525252';
  return <div className="calibration-shell calibration-shell--active items-center justify-center gap-layout p-inset text-center" style={{backgroundColor: color, position: 'fixed', inset: 0, zIndex: 90}}>
    <h1>{t('calibration.gazeTest.title')}</h1>
    <p role="status" aria-live="polite">{t(`calibration.gazeTest.${state}`)}</p>
    <p>{t('calibration.gazeTest.notice')}</p>
    {changed && <p role="alert">{t('calibration.gazeTest.recalibrate')}</p>}
    <div ref={areaRef} className="mx-auto w-full max-w-md border-2 border-white p-inset">
      <p>{t('calibration.gazeTest.area')}</p>
      <video ref={videoRef} autoPlay muted playsInline className="mx-auto w-full" aria-label={t('calibration.gazeTest.camera')} />
    </div>
    <div className="ui-button-group"><Button onClick={onRestart}>{t('calibration.restartCalibration')}</Button><Button variant="secondary" onClick={onExit}>{t('calibration.exitTitle')}</Button></div>
  </div>;
};
