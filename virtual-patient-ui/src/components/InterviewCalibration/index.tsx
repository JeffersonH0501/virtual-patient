import {CSSProperties, useEffect, useRef, useState} from 'react';
import {Navigate, useLocation, useNavigate, useParams} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {useInterviewMedia} from '../../contexts/interviewMedia';
import {useTechnicalCalibration} from '../../hooks/useTechnicalCalibration';
import {getInterview, saveCalibrationResult, startInterview} from '../../services/interviews';
import {createInterview} from '../../services/interviews/createInterview';
import {CompleteInterviewResponse} from '../../types/interview';
import {CalibrationRouteState, interviewPath, ROUTES} from '../../utils/routes';
import {Camera, Microphone, Warning} from '../../icons';
import {CalibrationInstructionsModal} from './CalibrationInstructionsModal';

type CheckState = 'ready' | 'warning' | 'unavailable';
const WAVEFORM_BAR_COUNT = 80;

const CalibrationCheck = ({label, state}: {label: string; state: CheckState}) => (
  <li className="calibration-check">
    <span className={`calibration-check__dot calibration-check__dot--${state}`} aria-hidden="true" />
    <span>{label}</span>
  </li>
);

export const InterviewCalibration = () => {
  const {t, i18n} = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const {interviewId: interviewIdParam} = useParams<{interviewId: string}>();
  // Legacy flow: the interview already exists and its id is in the URL.
  // New flow (/cases/calibration): no id yet; the case configuration arrives via
  // location.state and the interview is created only when the simulation starts.
  const hasInterviewId = Boolean(interviewIdParam);
  const interviewId = interviewIdParam ? Number.parseInt(interviewIdParam, 10) : Number.NaN;
  const routeConfig = (location.state as CalibrationRouteState | null) ?? null;
  const videoRef = useRef<HTMLVideoElement>(null);
  const saveRequestRef = useRef(0);
  const waveformSampleAtRef = useRef(0);
  const [interview, setInterview] = useState<CompleteInterviewResponse | null>(null);
  const [loading, setLoading] = useState(hasInterviewId);
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(!hasInterviewId);
  const [saveError, setSaveError] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [instructionsOpen, setInstructionsOpen] = useState(true);
  const [microphoneWaveform, setMicrophoneWaveform] = useState<number[]>([]);
  const media = useInterviewMedia();
  const calibration = useTechnicalCalibration(media.microphoneStream, media.cameraStream);
  const language: 'en' | 'es' = i18n.resolvedLanguage?.startsWith('es') ? 'es' : 'en';

  // In the new flow there is no interview to load, but the config must be present.
  const missingConfig = !hasInterviewId && !routeConfig;

  useEffect(() => {
    if (!hasInterviewId) return undefined;
    if (!Number.isFinite(interviewId)) {
      setLoading(false);
      setLoadError(true);
      return undefined;
    }
    let active = true;
    void getInterview(String(interviewId), language)
      .then((value) => {
        if (active) setInterview(value);
      })
      .catch(() => {
        if (active) setLoadError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [hasInterviewId, interviewId, language]);

  useEffect(() => {
    if (instructionsOpen || missingConfig) return;
    // Legacy flow only starts devices for the owner of an in-progress,
    // not-yet-started interview; the new flow always starts them (there is no
    // interview yet).
    if (hasInterviewId && (!interview || !interview.isOwner || interview.status !== 'in_progress' || interview.startTime)) {
      return;
    }
    void Promise.all([media.startCamera(), media.startMicrophone()]);
  }, [hasInterviewId, instructionsOpen, interview, media.startCamera, media.startMicrophone, missingConfig]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = media.cameraStream;
  }, [media.cameraStream]);

  useEffect(() => {
    const now = performance.now();
    if (now - waveformSampleAtRef.current < 120) return;
    waveformSampleAtRef.current = now;
    setMicrophoneWaveform((current) => [
      ...current.slice(-(WAVEFORM_BAR_COUNT - 1)),
      calibration.audioLevel,
    ]);
  }, [calibration.audioLevel]);

  useEffect(() => {
    if (!calibration.result) return;
    // New flow: nothing is persisted yet. The result is kept in the hook state
    // and saved together with interview creation when the simulation starts.
    if (!hasInterviewId) {
      setSaved(true);
      return;
    }
    if (!Number.isFinite(interviewId)) return;
    const requestId = ++saveRequestRef.current;
    setSaving(true);
    setSaved(false);
    setSaveError(false);
    void saveCalibrationResult(interviewId, calibration.result)
      .then((value) => {
        if (requestId !== saveRequestRef.current) return;
        setInterview((current) => current ? {
          ...current,
          interviewMetadata: value.interviewMetadata,
        } : current);
        setSaved(true);
      })
      .catch(() => {
        if (requestId === saveRequestRef.current) setSaveError(true);
      })
      .finally(() => {
        if (requestId === saveRequestRef.current) setSaving(false);
      });
  }, [calibration.result, hasInterviewId, interviewId]);

  // New flow reached without configuration (e.g. a direct URL hit): go back.
  if (missingConfig) return <Navigate to={ROUTES.clinicalCases} replace />;

  if (hasInterviewId) {
    if (loading) return <div className="calibration-state" role="status">{t('common.loading')}</div>;
    if (loadError || !interview) return <Navigate to={ROUTES.interviews} replace />;
    if (interview.status === 'completed') return <Navigate to={interviewPath(interview.id, 'review')} replace />;
    if (interview.startTime) return <Navigate to={interviewPath(interview.id, 'session')} replace />;
    if (!interview.isOwner) return <Navigate to={ROUTES.interviews} replace />;
  }

  const devicesReady = media.cameraState === 'ready' && media.microphoneState === 'ready';
  const isRecording = calibration.phase === 'recording';
  const result = calibration.result;
  const canContinue = Boolean(result?.status === 'passed' && saved && !saving && !starting);
  const secondsRemaining = Math.ceil(calibration.remainingMs / 1_000);
  const mediaError = [media.cameraState, media.microphoneState].some(
    (state) => state === 'permission-denied' || state === 'unavailable' || state === 'unsupported',
  );

  const retryDevices = () => {
    if (media.cameraState !== 'ready') void media.startCamera();
    if (media.microphoneState !== 'ready') void media.startMicrophone();
  };

  const onStartInterview = async () => {
    // Legacy flow: the interview already exists and its calibration is saved.
    if (hasInterviewId && interview) {
      navigate(interviewPath(interview.id, 'session'), {state: {justStarted: true}});
      return;
    }
    // New flow: create the interview now, persist the calibration result, start
    // it, and only then move to the session. This is the first time anything is
    // written for this interview.
    if (!routeConfig || !calibration.result || starting) return;
    setStarting(true);
    setStartError(null);
    try {
      const created = await createInterview({
        clinical_case_id: String(routeConfig.clinicalCaseId),
        patient_response_language: routeConfig.patientResponseLanguage,
        patient_gender: routeConfig.gender || undefined,
        personality_id: routeConfig.personalityId || undefined,
      });
      if (!created) throw new Error('missing-interview');
      const createdId = Number(created.id);
      await saveCalibrationResult(createdId, calibration.result);
      await startInterview(createdId);
      // Mark this as a fresh start so the session view does not treat the first
      // entry as a re-entry (which would prompt to resume or force termination).
      navigate(interviewPath(createdId, 'session'), {replace: true, state: {justStarted: true}});
    } catch (error) {
      const status = (error as {status?: number}).status;
      setStartError(
        status === 409
          ? t('clinicalSession.interviewInProgress')
          : t('clinicalSession.startFailed'),
      );
      setStarting(false);
    }
  };

  return (
    <>
      <CalibrationInstructionsModal
        isOpen={instructionsOpen}
        onAccept={() => setInstructionsOpen(false)}
        onCancel={() => navigate(ROUTES.clinicalCases)}
      />
      <section className="calibration-page" aria-labelledby="calibration-title">
      <header className="calibration-header">
        <div>
          <p className="calibration-eyebrow">{t('calibration.eyebrow')}</p>
          <h1 id="calibration-title" className="calibration-title">{t('calibration.title')}</h1>
          <p className="calibration-description">
            {t('calibration.instruction')}
          </p>
        </div>
      </header>

      <div className="calibration-grid">
        <article className="calibration-preview-card">
          <div className="calibration-preview">
            {media.cameraStream && media.cameraState === 'ready' ? (
              <video ref={videoRef} autoPlay muted playsInline aria-label={t('calibration.cameraPreview')} />
            ) : (
              <div className="calibration-preview__empty">
                <Camera color="currentColor" />
                <span>{t(`calibration.deviceStates.${media.cameraState}`)}</span>
              </div>
            )}
            {isRecording && <span className="calibration-recording-badge">{t('calibration.recording')}</span>}
            {(isRecording || !result) && media.cameraState === 'ready' && (
              <span
                className="calibration-countdown"
                role="timer"
                aria-live={isRecording ? 'assertive' : 'off'}
                aria-label={t('calibration.remaining', {seconds: secondsRemaining})}
              >
                {secondsRemaining}
              </span>
            )}
          </div>
          <div className="calibration-meter">
            <div className="voice-wave calibration-waveform" role="meter" aria-label={t('calibration.audioLevel')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(calibration.audioLevel * 100)}>
              {Array.from({length: WAVEFORM_BAR_COUNT}, (_, index) => {
                const level = microphoneWaveform[index] ?? 0.025;
                return (
                  <span
                    key={index}
                    data-wave-idle={microphoneWaveform[index] === undefined || undefined}
                    style={{'--wave-level': level} as CSSProperties}
                  />
                );
              })}
            </div>
          </div>
        </article>

        <article className="calibration-panel">
          <div className="calibration-device-columns">
            <section>
              <h2><Microphone color="currentColor" />{t('calibration.audio')}</h2>
              <ul>
                <CalibrationCheck label={t('calibration.checks.microphoneAvailable')} state={media.microphoneState === 'ready' ? 'ready' : 'unavailable'} />
                <CalibrationCheck label={t('calibration.checks.microphoneActive')} state={media.microphoneStream?.active ? 'ready' : 'unavailable'} />
                <CalibrationCheck
                  label={t(
                    calibration.voiceDetected
                      ? 'calibration.checks.voiceDetected'
                      : result
                        ? 'calibration.checks.voiceNotDetected'
                        : isRecording
                          ? 'calibration.checks.voiceChecking'
                          : 'calibration.checks.voiceReadyToCheck',
                  )}
                  state={calibration.voiceDetected ? 'ready' : result ? 'unavailable' : 'warning'}
                />
                <CalibrationCheck
                  label={t(result ? `calibration.checks.inputLevel.${result.audio.inputLevel}` : 'calibration.checks.inputLevel.pending')}
                  state={result ? (result.audio.inputLevel === 'adequate' ? 'ready' : 'unavailable') : 'warning'}
                />
                <CalibrationCheck
                  label={t(result?.audio.clippingDetected ? 'calibration.checks.clippingDetected' : result ? 'calibration.checks.noClipping' : 'calibration.checks.clippingPending')}
                  state={result ? (result.audio.clippingDetected ? 'unavailable' : 'ready') : 'warning'}
                />
              </ul>
            </section>
            <section>
              <h2><Camera color="currentColor" />{t('calibration.video')}</h2>
              <ul>
                <CalibrationCheck label={t('calibration.checks.cameraAvailable')} state={media.cameraState === 'ready' ? 'ready' : 'unavailable'} />
                <CalibrationCheck label={t('calibration.checks.videoActive')} state={media.cameraStream?.active ? 'ready' : 'unavailable'} />
                <CalibrationCheck
                  label={t(calibration.faceDetected ? 'calibration.checks.faceDetected' : isRecording ? 'calibration.checks.faceChecking' : result ? 'calibration.checks.faceNotDetected' : 'calibration.checks.faceReadyToCheck')}
                  state={calibration.faceDetected ? 'ready' : result ? 'unavailable' : 'warning'}
                />
                <CalibrationCheck
                  label={t('calibration.checks.faceDetectionRate', {rate: calibration.faceDetectionRate.toFixed(0)})}
                  state={result ? (result.video.qualityStatus === 'adequate' ? 'ready' : 'unavailable') : 'warning'}
                />
                <CalibrationCheck
                  label={t(result?.video.qualityStatus === 'adequate' ? 'calibration.checks.videoQualityAdequate' : result ? 'calibration.checks.videoQualityInadequate' : 'calibration.checks.videoQualityPending')}
                  state={result ? (result.video.qualityStatus === 'adequate' ? 'ready' : 'unavailable') : 'warning'}
                />
              </ul>
            </section>
          </div>

          {mediaError && (
            <div className="calibration-message calibration-message--error" role="alert">
              <Warning color="currentColor" />
              <span>{t('calibration.deviceError')}</span>
              <button type="button" onClick={retryDevices}>{t('calibration.retryDevices')}</button>
            </div>
          )}

          {result && (
            <div className={`calibration-result calibration-result--${result.status}`} role="status">
              <p>{t(result.status === 'passed' ? 'calibration.resultReadyDescription' : 'calibration.resultProblemDescription')}</p>
              {result.audio.inputLevel !== 'adequate' && <p className="calibration-result__warning">{t(`calibration.quality.${result.audio.inputLevel}`)}</p>}
              {result.audio.clippingDetected && <p className="calibration-result__warning">{t('calibration.quality.clipping')}</p>}
            </div>
          )}

          {(calibration.phase === 'error' || saveError) && (
            <p className="calibration-message calibration-message--error" role="alert">{t(saveError ? 'calibration.saveError' : 'calibration.recordingError')}</p>
          )}

          {startError && (
            <p className="calibration-message calibration-message--error" role="alert">{startError}</p>
          )}

          <footer className="calibration-actions">
            <button type="button" className="dialog-action dialog-action--secondary" onClick={() => navigate(ROUTES.clinicalCases)} disabled={isRecording || saving || starting}>{t('common.cancel')}</button>
            {canContinue ? (
              <button type="button" className="dialog-action dialog-action--primary" onClick={() => void onStartInterview()} disabled={starting}>{t(starting ? 'calibration.saving' : 'calibration.startInterview')}</button>
            ) : result ? (
              <button type="button" className="dialog-action dialog-action--primary" onClick={() => void calibration.start()} disabled={saving || !devicesReady || isRecording}>{t(saving ? 'calibration.saving' : 'calibration.repeat')}</button>
            ) : (
              <button type="button" className="dialog-action dialog-action--primary" onClick={() => void calibration.start()} disabled={!devicesReady || isRecording}>{isRecording ? t('calibration.calibrating') : t('calibration.startCalibration')}</button>
            )}
          </footer>
        </article>
      </div>
      </section>
    </>
  );
};
