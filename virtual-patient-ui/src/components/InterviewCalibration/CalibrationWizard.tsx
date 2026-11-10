import {Dialog} from '../common/Dialog';
import {Button} from '../common/Button';
import {FC, RefObject, useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Camera, Check, TriangleAlert} from 'lucide-react';
import {CalibrationPhase, GuidedCheckKind, GuidedCheckEnvironment} from '../../hooks/useTechnicalCalibration';
import {GuidedCheckDiagnostics} from '../../services/interviews/calibration';
import {MediaAccessState} from '../../contexts/interviewMedia';

// This visual activity threshold does not validate speech or calibration quality.
const SOUND_ACTIVITY_LEVEL = 0.08;

type CameraPreviewProps = {
  stream: MediaStream | null;
  state: MediaAccessState;
  compact?: boolean;
  soundActive?: boolean;
};

export const CameraPreview: FC<CameraPreviewProps> = ({
  stream,
  state,
  compact = false,
  soundActive = false,
}) => {
  const {t} = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = stream;
  }, [stream]);

  return (
    <div
      className={`calibration-camera ${compact ? 'calibration-camera--compact' : ''}`}
      data-sound-active={soundActive}
    >
      {stream ? (
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          aria-label={t('calibration.cameraPreview')}
        />
      ) : (
        <div className="calibration-camera__empty">
          <Camera />
          <span>{t(`calibration.wizard.deviceStates.${state}`)}</span>
        </div>
      )}
    </div>
  );
};

const DeviceStatus: FC<{
  icon: 'camera' | 'microphone';
  state: MediaAccessState;
  onRetry: () => void;
  devices: MediaDeviceInfo[];
  deviceId: string;
  onSelect: (deviceId: string) => void;
}> = ({icon, state, onRetry, devices, deviceId, onSelect}) => {
  const {t} = useTranslation();
  const ready = state === 'ready';
  const failed = ['permission-denied', 'unavailable', 'unsupported'].includes(state);
  const title = t(`calibration.wizard.devices.${icon}`);
  return (
    <div className="calibration-device-status" data-ready={ready} data-failed={failed}>
      <span className="calibration-device-status__copy">
        <strong>{title}</strong>
        <select
          className="ui-select calibration-device-status__select"
          aria-label={title}
          value={deviceId}
          disabled={state === 'loading' || state === 'unsupported' || (!devices.length && !deviceId)}
          onChange={(event) => onSelect(event.currentTarget.value)}
        >
          <option value="">{t('calibration.defaultDevice')}</option>
          {deviceId && !devices.some((device) => device.deviceId === deviceId) && (
            <option value={deviceId} disabled>{t('calibration.disconnectedDevice')}</option>
          )}
          {devices.map((device, index) => (
            <option key={device.deviceId} value={device.deviceId}>
              {device.label || `${title} ${index + 1}`}
            </option>
          ))}
        </select>
        <span className="calibration-device-status__message">
          <small>{t(`calibration.wizard.deviceStates.${state}`)}</small>
          {failed && (
            <button
              type="button"
              className="calibration-device-status__retry"
              aria-label={`${t('calibration.retryDevices')} · ${title}`}
              onClick={onRetry}
            >
              {t('calibration.retryDevices')}
            </button>
          )}
        </span>
      </span>
    </div>
  );
};

type PreparationProps = {
  audioLevel: number;
  cameraStream: MediaStream | null;
  cameraState: MediaAccessState;
  microphoneState: MediaAccessState;
  devicesReady: boolean;
  onStart: () => void;
  onStartGuided?: (environment: GuidedCheckEnvironment) => void;
  guidedOnly?: boolean;
  onBack: () => void;
  onRetryCamera: () => void;
  onRetryMicrophone: () => void;
  cameraDeviceId: string;
  microphoneDeviceId: string;
  onSelectCamera: (deviceId: string) => void;
  onSelectMicrophone: (deviceId: string) => void;
};

export const CalibrationPreparation: FC<PreparationProps> = ({
  audioLevel,
  cameraStream,
  cameraState,
  microphoneState,
  devicesReady,
  onStart,
  onStartGuided,
  guidedOnly = false,
  onBack,
  onRetryCamera,
  onRetryMicrophone,
  cameraDeviceId,
  microphoneDeviceId,
  onSelectCamera,
  onSelectMicrophone,
}) => {
  const {t} = useTranslation();
  const [informationOpen, setInformationOpen] = useState(true);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  useEffect(() => {
    const mediaDevices = navigator.mediaDevices;
    if (!mediaDevices?.enumerateDevices) return;
    let current = true;
    let request = 0;
    const refresh = async () => {
      const id = ++request;
      const available = await mediaDevices.enumerateDevices().catch(() => []);
      if (current && id === request) setDevices(available.filter((device) => device.deviceId));
    };
    void refresh();
    mediaDevices.addEventListener('devicechange', refresh);
    return () => {
      current = false;
      mediaDevices.removeEventListener('devicechange', refresh);
    };
  }, [cameraState, microphoneState]);
  return (
    <div className="calibration-shell calibration-shell--preparation">
      <Dialog
        title={t('calibration.wizard.information.title')}
        open={informationOpen}
        onClose={onBack}
        hasDismissAction
        containerId="calibration-information-dialog"
        actions={
          <>
            <Button variant="secondary" onClick={onBack}>
              {t('calibration.wizard.information.back')}
            </Button>
            <Button onClick={() => setInformationOpen(false)}>
              {t('calibration.wizard.information.acknowledge')}
            </Button>
          </>
        }
      >
        <p className="dialog-copy">{t('calibration.wizard.information.description')}</p>
        <p className="dialog-copy mt-layout">{t('calibration.wizard.information.introduction')}</p>
        <ul className="dialog-list dialog-copy mt-layout">
          <li><strong>{t('calibration.wizard.information.gaze.title')}:</strong> {t('calibration.wizard.information.gaze.description')}</li>
          <li><strong>{t('calibration.wizard.information.camera.title')}:</strong> {t('calibration.wizard.information.camera.description')}</li>
        </ul>
      </Dialog>
      {!informationOpen && <div className="calibration-preparation-grid">
        <div className="calibration-preparation-media">
          <CameraPreview
            stream={cameraStream}
            state={cameraState}
            soundActive={
              cameraState === 'ready' &&
              microphoneState === 'ready' &&
              audioLevel > SOUND_ACTIVITY_LEVEL
            }
          />
        </div>
        <div className="calibration-device-list">
          <DeviceStatus icon="camera" state={cameraState} onRetry={onRetryCamera} devices={devices.filter(({kind}) => kind === 'videoinput')} deviceId={cameraDeviceId} onSelect={onSelectCamera} />
          <DeviceStatus icon="microphone" state={microphoneState} onRetry={onRetryMicrophone} devices={devices.filter(({kind}) => kind === 'audioinput')} deviceId={microphoneDeviceId} onSelect={onSelectMicrophone} />
        </div>
        {onStartGuided && <p className="dialog-copy">{t('calibration.guided.introduction')}</p>}
        <div className="ui-button-group calibration-primary-actions">
          {onStartGuided && <button type="button" className="ui-button ui-button--secondary" onClick={() => onStartGuided({deviceType: 'laptop', cameraPosition: 'top'})} disabled={!devicesReady}>
            {t('calibration.guided.start')}
          </button>}
          {!guidedOnly && <button
            type="button"
            className="ui-button ui-button--primary"
            onClick={onStart}
            disabled={!devicesReady}
          >
            {t('calibration.startCalibration')}
          </button>}
        </div>
      </div>}
    </div>
  );
};

type ActiveStepProps = {
  phase: Exclude<CalibrationPhase, 'idle' | 'complete' | 'error'>;
  seconds: number;
  titleRef: RefObject<HTMLHeadingElement | null>;
  activeCheck?: GuidedCheckKind | null;
  remainingMs?: number;
  waitingForStep?: boolean;
  onStartStep?: () => void;
};

export const CalibrationActiveStep: FC<ActiveStepProps> = ({
  phase,
  seconds,
  titleRef,
  activeCheck,
  remainingMs = 0,
  waitingForStep = false,
  onStartStep,
}) => {
  const {t} = useTranslation();
  const step =
    phase === 'gaze_targets' || phase === 'gaze_preparation'
      ? 'gaze'
      : 'camera';
  return (
    <div
      className={`calibration-shell calibration-shell--active calibration-shell--${phase === 'guided_check' ? 'guided' : step}${phase === 'gaze_preparation' ? ' calibration-shell--gaze-preparation' : ''}`}
    >
      <div className="calibration-active-stage" aria-live="polite">
        {phase !== 'gaze_targets' && (
          <header key={step} className="calibration-active-copy motion-enter">
            <h1 ref={titleRef} tabIndex={-1}>
              {t(phase === 'guided_check' ? `calibration.guided.${activeCheck?.startsWith('gaze_') ? 'orientationSteps' : 'steps'}.${activeCheck}.title` : `calibration.wizard.${step}.title`)}
            </h1>
            {phase === 'gaze_preparation' && (
              <strong>{t('calibration.wizard.gaze.startsIn', {seconds})}</strong>
            )}
            {phase === 'guided_check' && <>
              <p>{t(`calibration.guided.${activeCheck?.startsWith('gaze_') ? 'orientationSteps' : 'steps'}.${activeCheck}.instruction`)}</p>
              {waitingForStep ? <Button onClick={onStartStep}>{t('calibration.guided.startStep')}</Button>
                : <strong>{t('calibration.guided.remaining', {seconds})}</strong>}
              {!waitingForStep && activeCheck === 'nod_three' && <strong>{t(remainingMs > 9000 ? 'calibration.guided.nodReady' : 'calibration.guided.nodNow',
                {number: Math.min(3, Math.floor((10000 - remainingMs - 1000) / 3000) + 1)})}</strong>}
            </>}
          </header>
        )}
      </div>
    </div>
  );
};

export const GuidedCheckResults: FC<{diagnostics: GuidedCheckDiagnostics}> = ({diagnostics}) => {
  const {t} = useTranslation();
  const percentage = (value: number | null) => value == null ? t('clinicalChat.recap.notAvailable') : `${Math.round(value * 100)}%`;
  return <section className="dialog-reading-card text-neutral-800" aria-label={t('calibration.guided.resultsTitle')}>
    <p>{t('calibration.guided.resultsDescription')}</p>
    {diagnostics.processingTimeSeconds != null && <p>{t('calibration.guided.processingTime', {seconds: diagnostics.processingTimeSeconds.toFixed(2)})}</p>}
    {diagnostics.environment && <p>{t('calibration.guided.environment', {
      device: t(`calibration.guided.devices.${diagnostics.environment.deviceType}`),
      camera: t(`calibration.guided.cameras.${diagnostics.environment.cameraPosition}`),
      orientation: t(`calibration.guided.orientations.${diagnostics.geometry?.orientation ?? 'unknown'}`),
    })}</p>}
    <dl>
      {diagnostics.phases.map((phase) => <div className="turn-detail-row" key={phase.kind}>
        <dt>{t(`calibration.guided.${diagnostics.version === 'guided_checks_v4_orientation' && phase.kind.startsWith('gaze_') ? 'orientationSteps' : 'steps'}.${phase.kind}.title`)}</dt>
        <dd>{phase.kind.startsWith('nod_') || phase.kind === 'head_shake'
          ? t('calibration.guided.nodComparison', {detected: phase.nodCount ?? t('clinicalChat.recap.notAvailable'), expected: phase.promptedNodCount})
          : t(phase.kind.startsWith('gaze_') ? 'calibration.guided.gazeCoverage' : 'calibration.guided.smileActivity',
            {value: percentage(phase.kind.startsWith('gaze_') ? phase.gazeValidRatio : phase.smileActivityRatio)})}</dd>
        {phase.kind.startsWith('gaze_') && phase.gazeErrorMedian != null && <span>{t('calibration.guided.gazeError', {value: phase.gazeErrorMedian.toFixed(3)})}</span>}
        {phase.sampleCount != null && <dd>{t('calibration.guided.samples', {count: phase.sampleCount, face: percentage(phase.faceValidRatio ?? null)})}</dd>}
        {(phase.kind.startsWith('nod_') || phase.kind === 'head_shake') && phase.nodWindowCoverage != null && <dd>{t('calibration.guided.nodCoverage', {coverage: percentage(phase.nodWindowCoverage), count: phase.nodEvaluableWindows ?? 0})}</dd>}
        {phase.nodUnavailableReason && <dd>{t(`calibration.guided.nodReasons.${phase.nodUnavailableReason}`, {defaultValue: t('calibration.guided.nodReasons.unknown')})}</dd>}
        {phase.kind.startsWith('smile_') && phase.meanSmileActivation != null && <dd>{t('calibration.guided.smileMean', {value: percentage(phase.meanSmileActivation)})}</dd>}
      </div>)}
    </dl>
  </section>;
};

type CheckpointProps = {
  stage: 'gaze' | 'camera';
  passed?: boolean;
  experimentalOverride?: boolean;
  failureReason?: string | null;
  diagnostics?: unknown;
  onStart: () => void;
  onContinue?: () => void;
  onRestart?: () => void;
  busy?: boolean;
  error?: boolean;
  titleRef: RefObject<HTMLHeadingElement | null>;
  guidedDiagnostics?: GuidedCheckDiagnostics | null;
  guidedVideoUrl?: string | null;
  continueLabel?: string;
};

export const CalibrationCheckpoint: FC<CheckpointProps> = ({
  stage,
  passed,
  experimentalOverride = false,
  failureReason,
  diagnostics,
  onStart,
  onContinue,
  onRestart,
  busy = false,
  error = false,
  titleRef,
  guidedDiagnostics,
  guidedVideoUrl,
  continueLabel,
}) => {
  const {t} = useTranslation();
  const hasResult = passed !== undefined;
  const quality = diagnostics && typeof diagnostics === 'object' ? diagnostics as Record<string, unknown> : {};
  const targets = quality.targets && typeof quality.targets === 'object' ? quality.targets as Record<string, {eligible?: boolean; validSamples?: number; validRatio?: number; validDurationMs?: number}> : {};
  const unavailableTargets = Object.entries(targets).filter(([, target]) => target.eligible === false);
  const precision = quality.leaveOneTargetOut as {medianNormalizedError?: number; p90NormalizedError?: number; perTarget?: Record<string, {p90NormalizedError?: number}>} | undefined;
  const limits = quality.qualityLimits as {medianNormalizedError?: number; p90NormalizedError?: number} | undefined;
  const percent = (value?: number) => value == null ? '—' : `${(value * 100).toFixed(1)}%`;


  let retryLabel = 'calibration.startStep';
  if (hasResult) retryLabel = stage === 'camera' && failureReason !== 'geometry' ? 'calibration.retryCamera' : 'calibration.repeatStep';
  if (failureReason === 'upload_failed') retryLabel = 'calibration.retryUpload';
  return (
    <div className="calibration-shell calibration-shell--active calibration-shell--checkpoint">
      <div className={`calibration-checkpoint-content motion-enter${guidedDiagnostics ? ' calibration-checkpoint-content--guided' : ''}`}>
        {hasResult && (
          <div
            className={`calibration-checkpoint-symbol ${passed && !experimentalOverride ? 'is-success' : 'is-failure'}`}
            aria-hidden="true"
          >
            {passed && !experimentalOverride ? <Check /> : <TriangleAlert />}
          </div>
        )}
        <h1 ref={titleRef} tabIndex={-1}>
          {t(
            experimentalOverride ? 'calibration.diagnostics.experimentalTitle' : hasResult && passed ? 'calibration.wizard.success.title' : hasResult && failureReason !== 'upload_failed' && failureReason !== 'draft_create_failed' ? `calibration.wizard.failures.${failureCategory(failureReason ?? null, stage)}.title` : `calibration.wizard.${stage}.${hasResult ? 'failedTitle' : 'readyTitle'}`,
          )}
        </h1>
        {experimentalOverride && <p>{t('calibration.diagnostics.experimentalNotice')}</p>}
        {!(hasResult && passed) && (
          <p>
            {hasResult && !passed
              ? t(
                  failureReason === 'upload_too_large'
                    ? 'calibration.uploadTooLarge'
                    : failureReason === 'upload_failed'
                    ? 'calibration.uploadError'
                    : failureReason === 'draft_create_failed'
                      ? 'calibration.draftCreateError'
                      : `calibration.wizard.failures.${failureCategory(failureReason ?? null, stage)}.advice`,
                )
              : t(
                  `calibration.wizard.${stage}.readyDescription`,
                )}
          </p>
        )}
        {(passed === false || experimentalOverride) && unavailableTargets.length > 0 && (
          <p>{t('calibration.diagnostics.targets', {targets: unavailableTargets.map(([name]) => t(`calibration.targetNames.${name}`)).join(', ')})}</p>
        )}
        {failureReason === 'capture_quality' && <p>{t('calibration.diagnostics.captureQuality')}</p>}
        {hasResult && ['mediapipe_five_point_quality_v1', 'mediapipe_five_point_quality_v2'].includes(String(quality.version)) && <details className="w-full text-left">
          <summary>{t('calibration.diagnostics.qualityTitle')}</summary>
          <p>{t('calibration.diagnostics.precision', {median: percent(precision?.medianNormalizedError), p90: percent(precision?.p90NormalizedError),
            medianLimit: percent(limits?.medianNormalizedError), p90Limit: percent(limits?.p90NormalizedError)})}</p>
          <div className="overflow-auto"><table className="w-full text-left">
            <thead><tr>{['point', 'samples', 'coverage', 'support', 'p90'].map((key) => <th scope="col" className="p-2" key={key}>{t(`calibration.diagnostics.${key}`)}</th>)}</tr></thead>
            <tbody>{Object.entries(targets).map(([name, target]) => <tr key={name}>
              <th scope="row" className="p-2">{t(`calibration.targetNames.${name}`)}</th>
              <td className="p-2">{target.validSamples ?? '—'}</td><td className="p-2">{percent(target.validRatio)}</td>
              <td className="p-2">{target.validDurationMs == null ? '—' : `${(target.validDurationMs / 1000).toFixed(2)} s`}</td>
              <td className="p-2">{percent(precision?.perTarget?.[name]?.p90NormalizedError)}</td>
            </tr>)}</tbody>
          </table></div>
          <p>{t('calibration.diagnostics.errorNote')}</p>
          {typeof quality.cameraRadiusP90 === 'number' && <p>{t('calibration.diagnostics.cameraQuality', {
            radius: quality.cameraRadiusP90.toFixed(4), limit: Number(quality.cameraRadiusLimit).toFixed(4),
            seconds: (Number(quality.cameraValidDurationMs) / 1000).toFixed(2)})}</p>}
        </details>}
        {error && (
          <p className="calibration-friendly-alert" role="alert">
            {t('clinicalSession.startFailed')}
          </p>
        )}
        {guidedDiagnostics && <div className="w-full text-left">
          {guidedVideoUrl && <video controls preload="metadata" src={guidedVideoUrl} className="mx-auto mb-layout max-h-64 w-full max-w-md" aria-label={t('calibration.guided.testVideo')} />}
          <GuidedCheckResults diagnostics={guidedDiagnostics} />
        </div>}
        <div className="calibration-primary-actions">
          {hasResult && passed && onRestart && (
            <Button variant="secondary" onClick={onRestart} disabled={busy}>
              {t('calibration.restartCalibration')}
            </Button>
          )}
          {hasResult && passed && onContinue && (
            <button
              type="button"
              className="ui-button ui-button--primary"
              onClick={onContinue}
              disabled={busy}
            >
              {busy ? t('calibration.saving') : continueLabel ?? t('calibration.startInterview')}
            </button>
          )}
          {(!hasResult || !passed) && (
            <button type="button" className="ui-button ui-button--primary" onClick={onStart} disabled={busy}>
              {t(retryLabel)}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export const CalibrationProcessing: FC<{
  titleRef: RefObject<HTMLHeadingElement | null>;
}> = ({titleRef}) => {
  const {t} = useTranslation();
  return (
    <div
      className="calibration-shell calibration-shell--processing"
      role="status"
      aria-live="polite"
    >
      <div className="calibration-processing-content motion-enter">
        <div className="calibration-processing-mark" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <h1 ref={titleRef} tabIndex={-1}>
          {t('calibration.wizard.processing.title')}
        </h1>
        <small>{t('calibration.wizard.processing.status')}</small>
      </div>
    </div>
  );
};

const failureCategory = (reason: string | null, stage?: 'gaze' | 'camera') => {
  if (reason === 'draft_expired') return 'draft';
  if (reason === 'camera_unstable') return 'cameraStability';
  if (reason === 'median_error' || reason === 'p90_error') return 'precision';
  if (reason === 'targets' || reason === 'insufficient_gaze_samples') return 'coverage';
  if (reason === 'capture_quality') return 'coverage';
  if (reason === 'timing_unstable') return 'timing';
  if (reason === 'recording_failed') return 'recording';
  if (reason === 'capture_interrupted') return 'interrupted';
  if (stage === 'camera' && (reason === 'face' || reason === 'camera')) return 'camera';
  if (reason === 'geometry') return 'geometry';
  if (reason === 'processing_failed') return 'processing';
  return 'gaze';
};
