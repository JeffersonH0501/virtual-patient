import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {ScanEye} from 'lucide-react';
import {useUser} from '../../hooks/useUser';
import {CalibrationReference, getCalibrationReference} from '../../services/interviews/calibrationReference';
import {resolveRecordingSource} from '../../services/recordings';
import {formatPlaybackTime} from '../../utils/duration';
import {Dialog} from '../common/Dialog';
import {Button} from '../common/Button';
import {InterviewContentLoading} from './InterviewContentLoading';
import {GuidedCheckResults} from '../InterviewCalibration/CalibrationWizard';
import {GuidedCheckDiagnostics} from '../../services/interviews/calibration';

const CalibrationVideo = ({source, label}: {source: string; label: string}) => {
  const {t} = useTranslation();
  const [failed, setFailed] = useState(false);
  return failed ? <p role="alert">{t('calibrationReference.videoUnavailable')}</p> :
    <video className="w-full rounded-lg bg-black" controls playsInline preload="metadata" src={resolveRecordingSource(source) ?? undefined} aria-label={label} onError={() => setFailed(true)} />;
};

const QualityResult = ({result, stage}: {result: Record<string, unknown>; stage: string}) => {
  const {t} = useTranslation();
  const quality = (result.quality ?? {}) as Record<string, unknown>;
  const metrics = ['coveredTargets', 'faceValidRatio', 'cameraFaceValidRatio', 'cameraValidDurationMs', 'cameraRadiusP90', 'cameraRadiusLimit'];
  const heldOut = (quality.leaveOneTargetOut ?? {}) as Record<string, unknown>;
  return <section className="space-y-2">
    <h4 className="default-title">{t(`calibrationReference.stages.${stage}`)}: {t(`calibrationReference.${result.passed === true ? 'passed' : 'failed'}`)}</h4>
    {result.experimentalQualityBypass === true && <p>{t('calibration.diagnostics.experimentalNotice')}</p>}
    <dl className="space-y-1">
      {[...metrics.map((key) => [key, quality[key]] as const), ...Object.entries(heldOut)].map(([key, value]) => typeof value === 'number' && Number.isFinite(value) ?
        <div key={key} className="flex flex-wrap justify-between gap-2"><dt>{t(`calibrationReference.metrics.${key}`)}</dt><dd>{Number(value.toFixed(3))}</dd></div> : null)}
    </dl>
  </section>;
};

export const CalibrationReferenceDialog = ({interviewId}: {interviewId: number}) => {
  const {user} = useUser();
  const {t} = useTranslation();
  const [open, setOpen] = useState(false);
  const [reference, setReference] = useState<CalibrationReference | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!open || user?.role !== 'superuser') return;
    const controller = new AbortController();
    setReference(null); setFailed(false);
    void getCalibrationReference(interviewId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setReference(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [open, interviewId, user?.role, attempt]);
  if (user?.role !== 'superuser') return null;
  const processingTimes = reference?.captures.map((capture) => capture.result?.processingTimeSeconds);
  const totalProcessingTime = processingTimes?.length && processingTimes.every((value) => typeof value === 'number' && Number.isFinite(value))
    ? processingTimes.reduce<number>((total, value) => total + (value as number), 0) : null;
  return <>
    <span className="panel-header-action">
      <button type="button" className="ui-icon-button" onClick={() => setOpen(true)}
        aria-label={t('calibrationReference.title')} title={t('calibrationReference.title')}
        aria-haspopup="dialog" aria-expanded={open}>
        <ScanEye aria-hidden="true" />
      </button>
    </span>
    <Dialog open={open} title={t('calibrationReference.title')} size="large" onClose={() => setOpen(false)}>
      {open && <div className="space-y-layout">
        {!reference && !failed && <InterviewContentLoading />}
        {failed && <div role="alert"><p>{t('calibrationReference.loadFailed')}</p><Button variant="secondary" onClick={() => setAttempt((value) => value + 1)}>{t('calibrationReference.retry')}</Button></div>}
        {reference && reference.captures.length === 0 && <p>{t('calibrationReference.empty')}</p>}
        {totalProcessingTime != null && <p>{t('calibration.guided.testProcessingTime', {seconds: totalProcessingTime.toFixed(2)})}</p>}
        {reference?.captures.map((capture, index) => <article key={capture.id} className="dialog-reading-card dialog-reading-card--compact space-y-layout bg-surface">
          <header className="space-y-1">
            <h3 className="default-title">{t('calibrationReference.capture', {number: index + 1})} · {t(`calibrationReference.stages.${capture.stage}`)}</h3>
            <p>{t('calibrationReference.duration')}: {formatPlaybackTime(capture.durationMs / 1000)}</p>
            {typeof capture.result?.processingTimeSeconds === 'number' && !capture.result.guidedChecks && <p>{t('calibration.guided.processingTime', {seconds: capture.result.processingTimeSeconds.toFixed(2)})}</p>}
            {capture.usedFor.length > 0 && <p>{t('calibrationReference.usedFor', {stages: capture.usedFor.map((stage) => t(`calibrationReference.stages.${stage}`)).join(', ')})}</p>}
          </header>
          {capture.mediaUrl ? <CalibrationVideo source={capture.mediaUrl} label={t('calibrationReference.capture', {number: index + 1})} /> : <p>{t('calibrationReference.videoUnavailable')}</p>}
          {Boolean(capture.result?.guidedChecks) && <GuidedCheckResults diagnostics={capture.result?.guidedChecks as GuidedCheckDiagnostics} />}
          {!capture.result ? <p>{t('calibrationReference.pending')}</p> : capture.stage === 'unified' && (capture.result.gaze || capture.result.camera) ?
            ['gaze', 'camera'].map((stage) => capture.result?.[stage] && typeof capture.result[stage] === 'object' ? <QualityResult key={stage} stage={stage} result={capture.result[stage] as Record<string, unknown>} /> : null) :
            <QualityResult stage={capture.stage} result={capture.result} />}
          <details><summary>{t('calibrationReference.details')}</summary><pre className="overflow-auto whitespace-pre-wrap break-words secondary-text">{JSON.stringify({metadata: capture.metadata, result: capture.result}, null, 2)}</pre></details>
        </article>)}
        {reference?.calibration && <details><summary>{t('calibrationReference.accepted')}</summary><pre className="overflow-auto whitespace-pre-wrap break-words secondary-text">{JSON.stringify(reference.calibration, null, 2)}</pre></details>}
      </div>}
    </Dialog>
  </>;
};
