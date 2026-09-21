import {CSSProperties, FC, RefObject, useEffect, useRef} from 'react';
import {useTranslation} from 'react-i18next';
import {Camera, Microphone, Warning} from '../../icons';
import {CalibrationPhase} from '../../hooks/useTechnicalCalibration';
import {MediaAccessState} from '../../contexts/interviewMedia';

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

const CalibrationProgress: FC<{activeStep: number}> = ({activeStep}) => {
  const {t} = useTranslation();
  const steps = ['preparation', 'gaze', 'camera', 'voice', 'ready'];
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
  titleRef: RefObject<HTMLHeadingElement | null>;
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
  titleRef,
}) => {
  const {t} = useTranslation();
  const deviceProblem =
    ['permission-denied', 'unavailable', 'unsupported'].includes(cameraState) ||
    ['permission-denied', 'unavailable', 'unsupported'].includes(microphoneState);
  return (
    <div className="calibration-shell calibration-shell--preparation">
      <CalibrationProgress activeStep={0} />
      <header className="calibration-hero">
        <p>{t('calibration.wizard.eyebrow')}</p>
        <h1 ref={titleRef} tabIndex={-1}>
          {t('calibration.wizard.preparation.title')}
        </h1>
        <span>{t('calibration.wizard.preparation.description')}</span>
      </header>
      <div className="calibration-preparation-grid">
        <CameraPreview stream={cameraStream} state={cameraState} />
        <aside className="calibration-preparation-panel">
          <div className="calibration-device-list">
            <DeviceStatus icon="camera" state={cameraState} />
            <DeviceStatus icon="microphone" state={microphoneState} />
          </div>
          <AudioLevelIndicator level={audioLevel} />
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
  targetOrder: number;
  cameraStream: MediaStream | null;
  cameraState: MediaAccessState;
  audioLevel: number;
  titleRef: RefObject<HTMLHeadingElement | null>;
};

export const CalibrationActiveStep: FC<ActiveStepProps> = ({
  phase,
  seconds,
  targetOrder,
  cameraStream,
  cameraState,
  audioLevel,
  titleRef,
}) => {
  const {t} = useTranslation();
  const step =
    phase === 'gaze_targets'
      ? 'gaze'
      : phase === 'camera_reference'
        ? 'camera'
        : phase === 'voice_baseline'
          ? 'voice'
          : 'validation';
  const progressStep = step === 'gaze' || step === 'validation' ? 1 : step === 'camera' ? 2 : 3;
  return (
    <div className={`calibration-shell calibration-shell--active calibration-shell--${step}`}>
      <CalibrationProgress activeStep={progressStep} />
      <div className="calibration-active-stage" aria-live="polite">
        <header className="calibration-active-copy">
          <h1 ref={titleRef} tabIndex={-1}>
            {t(`calibration.wizard.${step}.title`)}
          </h1>
          <p>{t(`calibration.wizard.${step}.description`)}</p>
          {step === 'gaze' && (
            <strong>{t('calibration.wizard.gaze.progress', {current: targetOrder})}</strong>
          )}
        </header>
        {step === 'gaze' ? (
          <div className="calibration-gaze-hint" aria-hidden="true">
            <CameraPreview stream={cameraStream} state={cameraState} compact />
          </div>
        ) : (
          <div className="calibration-active-media">
            <CameraPreview stream={cameraStream} state={cameraState} />
            {step === 'voice' && <AudioLevelIndicator level={audioLevel} large />}
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

export const CalibrationProcessing: FC<{titleRef: RefObject<HTMLHeadingElement | null>}> = ({
  titleRef,
}) => {
  const {t} = useTranslation();
  return (
    <div className="calibration-shell calibration-shell--centered" role="status" aria-live="polite">
      <div className="calibration-processing-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <h1 ref={titleRef} tabIndex={-1}>
        {t('calibration.wizard.processing.title')}
      </h1>
      <p>{t('calibration.wizard.processing.description')}</p>
      <div className="calibration-indeterminate" aria-hidden="true">
        <span />
      </div>
      <small>{t('calibration.wizard.processing.status')}</small>
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

const failureCategory = (reason: string | null) => {
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
