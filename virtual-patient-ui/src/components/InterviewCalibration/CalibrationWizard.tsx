import {CSSProperties, FC, RefObject, useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Camera, Microphone, Warning, X} from '../../icons';
import {CalibrationPhase} from '../../hooks/useTechnicalCalibration';
import {MediaAccessState} from '../../contexts/interviewMedia';
import {Modal} from '../common/Modal';

const WAVEFORM_BAR_COUNT = 52;

type CameraPreviewProps = {
  stream: MediaStream | null;
  state: MediaAccessState;
  compact?: boolean;
};

export const CameraPreview: FC<CameraPreviewProps> = ({stream, state, compact = false}) => {
  const {t} = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = stream;
  }, [stream]);

  return (
    <div className={`calibration-camera ${compact ? 'calibration-camera--compact' : ''}`}>
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
          <Camera color="currentColor" />
          <span>{t(`calibration.wizard.deviceStates.${state}`)}</span>
        </div>
      )}
    </div>
  );
};

export const AudioLevelIndicator: FC<{level: number; large?: boolean}> = ({
  level,
  large = false,
}) => {
  const {t} = useTranslation();
  return (
    <div
      className={`calibration-audio-level ${large ? 'calibration-audio-level--large' : ''}`}
      role="meter"
      aria-label={t('calibration.audioLevel')}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(level * 100)}
    >
      {Array.from({length: WAVEFORM_BAR_COUNT}, (_, index) => (
        <span
          key={index}
          style={
            {
              '--calibration-level': Math.max(0.06, level * (0.45 + ((index * 7) % 11) / 20)),
            } as CSSProperties
          }
        />
      ))}
    </div>
  );
};

const DeviceStatus: FC<{
  icon: 'camera' | 'microphone';
  state: MediaAccessState;
}> = ({icon, state}) => {
  const {t} = useTranslation();
  const ready = state === 'ready';
  return (
    <div className="calibration-device-status" data-ready={ready}>
      <span className="calibration-device-status__icon" aria-hidden="true">
        {icon === 'camera' ? <Camera color="currentColor" /> : <Microphone color="currentColor" />}
      </span>
      <span>
        <strong>{t(`calibration.wizard.devices.${icon}`)}</strong>
        <small>{t(`calibration.wizard.deviceStates.${state}`)}</small>
      </span>
    </div>
  );
};

export const CalibrationProgress: FC<{activeStep: number}> = ({activeStep}) => {
  const {t} = useTranslation();
  const steps = ['preparation', 'voice', 'gaze', 'camera'];
  return (
    <ol className="calibration-progress" aria-label={t('calibration.wizard.progressLabel')}>
      {steps.map((step, index) => (
        <li key={step} data-active={index === activeStep} data-complete={index < activeStep}>
          <span>{index + 1}</span>
          <small>{t(`calibration.wizard.steps.${step}`)}</small>
        </li>
      ))}
    </ol>
  );
};

type PreparationProps = {
  cameraStream: MediaStream | null;
  cameraState: MediaAccessState;
  microphoneState: MediaAccessState;
  audioLevel: number;
  devicesReady: boolean;
  onStart: () => void;
  onBack: () => void;
  onRetryDevices: () => void;
};

export const CalibrationPreparation: FC<PreparationProps> = ({
  cameraStream,
  cameraState,
  microphoneState,
  audioLevel,
  devicesReady,
  onStart,
  onBack,
  onRetryDevices,
}) => {
  const {t} = useTranslation();
  const [informationOpen, setInformationOpen] = useState(true);
  const deviceProblem =
    ['permission-denied', 'unavailable', 'unsupported'].includes(cameraState) ||
    ['permission-denied', 'unavailable', 'unsupported'].includes(microphoneState);
  return (
    <div className="calibration-shell calibration-shell--preparation">
      <Modal
        open={informationOpen}
        closeAction={() => setInformationOpen(false)}
        size="medium"
        containerId="calibration-information-dialog"
        ariaLabel={t('calibration.wizard.information.title')}
      >
        <div className="dialog-shell">
          <header className="dialog-header">
            <h2 className="dialog-title">{t('calibration.wizard.information.title')}</h2>
            <button
              type="button"
              className="dialog-close-button"
              onClick={() => setInformationOpen(false)}
              aria-label={t('common.close')}
              title={t('common.close')}
            >
              <span className="block h-5 w-5 [&_svg]:h-full [&_svg]:w-full">
                <X color="currentColor" />
              </span>
            </button>
          </header>
          <div className="dialog-content">
            <p className="dialog-copy">{t('calibration.wizard.information.description')}</p>
            <ol className="calibration-information-steps">
              {(['voice', 'gaze', 'camera'] as const).map((item, index) => (
                <li key={item}>
                  <div className="calibration-information-step-title">
                    <span aria-hidden="true">{index + 1}</span>
                    <strong>{t(`calibration.wizard.information.${item}.title`)}</strong>
                  </div>
                  <p>{t(`calibration.wizard.information.${item}.description`)}</p>
                </li>
              ))}
            </ol>
            <p className="dialog-annotation">{t('calibration.wizard.information.note')}</p>
          </div>
        </div>
      </Modal>
      <CalibrationProgress activeStep={0} />
      <div className="calibration-preparation-grid">
        <div className="calibration-preparation-media">
          <CameraPreview stream={cameraStream} state={cameraState} />
          <AudioLevelIndicator level={audioLevel} />
        </div>
        <aside className="calibration-preparation-panel">
          <div className="calibration-device-list">
            <DeviceStatus icon="camera" state={cameraState} />
            <DeviceStatus icon="microphone" state={microphoneState} />
          </div>
          {deviceProblem && (
            <div className="calibration-friendly-alert" role="alert">
              <Warning color="currentColor" />
              <p>{t('calibration.wizard.permissionsHelp')}</p>
              <button type="button" onClick={onRetryDevices}>
                {t('calibration.retryDevices')}
              </button>
            </div>
          )}
          <ul className="calibration-recommendations">
            {(['face', 'quiet', 'stable'] as const).map((item) => (
              <li key={item}>
                <span aria-hidden="true">✓</span>
                {t(`calibration.wizard.recommendations.${item}`)}
              </li>
            ))}
          </ul>
          <div className="calibration-primary-actions">
            <button
              type="button"
              className="calibration-button calibration-button--secondary"
              onClick={onBack}
            >
              {t('common.back')}
            </button>
            <button
              type="button"
              className="calibration-button calibration-button--primary"
              onClick={onStart}
              disabled={!devicesReady}
            >
              {t('calibration.startCalibration')}
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
};

type ActiveStepProps = {
  phase: CalibrationPhase;
  seconds: number;
  audioLevel: number;
  titleRef: RefObject<HTMLHeadingElement | null>;
};

export const CalibrationActiveStep: FC<ActiveStepProps> = ({
  phase,
  seconds,
  audioLevel,
  titleRef,
}) => {
  const {t} = useTranslation();
  const step =
    phase === 'gaze_targets' || phase === 'gaze_preparation'
      ? 'gaze'
      : phase === 'camera_reference'
        ? 'camera'
        : phase === 'voice_baseline'
          ? 'voice'
          : 'validation';
  const progressStep = step === 'voice' ? 1 : step === 'gaze' || step === 'validation' ? 2 : 3;
  return (
    <div className={`calibration-shell calibration-shell--active calibration-shell--${step}${phase === 'gaze_preparation' ? ' calibration-shell--gaze-preparation' : ''}`}>
      <CalibrationProgress activeStep={progressStep} />
      <div className="calibration-active-stage" aria-live="polite">
        {phase !== 'gaze_targets' && (
          <header className="calibration-active-copy">
            <h1 ref={titleRef} tabIndex={-1}>
              {t(`calibration.wizard.${step}.title`)}
            </h1>
            <p>{t(`calibration.wizard.${step}.description`)}</p>
            {phase === 'gaze_preparation' && (
              <strong>{t('calibration.wizard.gaze.startsIn', {seconds})}</strong>
            )}
          </header>
        )}
        {step === 'voice' && (
          <div className="calibration-active-media">
            <AudioLevelIndicator level={audioLevel} large />
          </div>
        )}
        {step !== 'gaze' && (
          <div
            className="calibration-stage-countdown"
            aria-label={t('calibration.remaining', {seconds})}
          >
            {seconds}
          </div>
        )}
        {step === 'voice' && (
          <p className="calibration-speaking-prompt">{t('calibration.wizard.voice.prompt')}</p>
        )}
      </div>
    </div>
  );
};

type CheckpointProps = {
  stage: 'gaze' | 'camera' | 'voice';
  activeStep: number;
  passed?: boolean;
  failureReason?: string | null;
  onStart: () => void;
  onContinue?: () => void;
  busy?: boolean;
  error?: boolean;
  titleRef: RefObject<HTMLHeadingElement | null>;
};

export const CalibrationCheckpoint: FC<CheckpointProps> = ({
  stage,
  activeStep,
  passed,
  failureReason,
  onStart,
  onContinue,
  busy = false,
  error = false,
  titleRef,
}) => {
  const {t} = useTranslation();
  const hasResult = passed !== undefined;
  return (
    <div className="calibration-shell calibration-shell--active calibration-shell--checkpoint">
      <CalibrationProgress activeStep={activeStep} />
      <div className="calibration-checkpoint-content">
        {hasResult && (
          <div className={`calibration-checkpoint-symbol ${passed ? 'is-success' : 'is-failure'}`} aria-hidden="true">
            {passed ? '✓' : '!'}
          </div>
        )}
        <h1 ref={titleRef} tabIndex={-1}>
          {t(`calibration.wizard.${stage}.${hasResult ? (passed ? 'passedTitle' : 'failedTitle') : 'readyTitle'}`)}
        </h1>
        <p>
          {hasResult && !passed
            ? t(`calibration.wizard.failures.${failureCategory(failureReason ?? null, stage)}.advice`)
            : t(`calibration.wizard.${stage}.${hasResult ? 'passedDescription' : 'readyDescription'}`)}
        </p>
        {error && (
          <p className="calibration-friendly-alert" role="alert">
            {t('clinicalSession.startFailed')}
          </p>
        )}
        <div className="calibration-primary-actions">
          {hasResult && passed && onContinue && (
            <button type="button" className="calibration-button calibration-button--primary" onClick={onContinue} disabled={busy}>
              {t(stage === 'camera' ? (busy ? 'calibration.saving' : 'calibration.startInterview') : 'calibration.nextStep')}
            </button>
          )}
          {(!hasResult || !passed) && (
            <button type="button" className="calibration-button calibration-button--primary" onClick={onStart}>
              {t(hasResult ? 'calibration.repeatStep' : 'calibration.startStep')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export const CalibrationProcessing: FC<{
  stage: 'gaze' | 'camera' | 'voice';
  activeStep: number;
  titleRef: RefObject<HTMLHeadingElement | null>;
}> = ({stage, activeStep, titleRef}) => {
  const {t} = useTranslation();
  return (
    <div className="calibration-shell calibration-shell--processing" role="status" aria-live="polite">
      <CalibrationProgress activeStep={activeStep} />
      <div className="calibration-processing-content">
        <div className="calibration-processing-mark" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <h1 ref={titleRef} tabIndex={-1}>
          {t(`calibration.wizard.processing.${stage}.title`)}
        </h1>
        <p>{t(`calibration.wizard.processing.${stage}.description`)}</p>
        <small>{t('calibration.wizard.processing.status')}</small>
      </div>
    </div>
  );
};

type ResultProps = {
  passed: boolean;
  failureReason: string | null;
  busy: boolean;
  error: boolean;
  onContinue: () => void;
  onRetry: () => void;
  onBack: () => void;
  titleRef: RefObject<HTMLHeadingElement | null>;
};

const failureCategory = (reason: string | null, stage?: 'gaze' | 'camera' | 'voice') => {
  if (stage === 'camera' && (reason === 'face' || reason === 'camera')) return 'camera';
  if (reason === 'geometry') return 'geometry';
  if (reason === 'speech' || reason === 'insufficient_audio') return 'speech';
  if (reason === 'clipping') return 'clipping';
  if (reason === 'processing_failed') return 'processing';
  return 'gaze';
};

export const CalibrationResult: FC<ResultProps> = ({
  passed,
  failureReason,
  busy,
  error,
  onContinue,
  onRetry,
  onBack,
  titleRef,
}) => {
  const {t} = useTranslation();
  const category = failureCategory(failureReason);
  return (
    <div
      className={`calibration-shell calibration-shell--centered calibration-shell--result ${passed ? 'is-success' : 'is-failure'}`}
    >
      <CalibrationProgress activeStep={passed ? 4 : 0} />
      <div className="calibration-result-symbol" aria-hidden="true">
        {passed ? '✓' : '!'}
      </div>
      <h1 ref={titleRef} tabIndex={-1}>
        {t(
          passed
            ? 'calibration.wizard.success.title'
            : `calibration.wizard.failures.${category}.title`,
        )}
      </h1>
      <p>
        {t(
          passed
            ? 'calibration.wizard.success.description'
            : `calibration.wizard.failures.${category}.advice`,
        )}
      </p>
      {error && (
        <p className="calibration-friendly-alert" role="alert">
          {t('clinicalSession.startFailed')}
        </p>
      )}
      <div className="calibration-primary-actions">
        {!passed && (
          <button
            type="button"
            className="calibration-button calibration-button--secondary"
            onClick={onBack}
          >
            {t('common.back')}
          </button>
        )}
        <button
          type="button"
          className="calibration-button calibration-button--primary"
          onClick={passed ? onContinue : onRetry}
          disabled={busy}
        >
          {t(
            passed
              ? busy
                ? 'calibration.saving'
                : 'calibration.startInterview'
              : 'calibration.repeat',
          )}
        </button>
      </div>
    </div>
  );
};
