import {CSSProperties, useCallback, useEffect, useRef, useState} from 'react';
import {Navigate, useLocation, useNavigate, useParams} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {useInterviewMedia} from '../../contexts/interviewMedia';
import {useTechnicalCalibration} from '../../hooks/useTechnicalCalibration';
import {getInterview, processTemporaryCalibration, saveCalibrationResult, startInterview} from '../../services/interviews';
import {CalibrationDraft, CalibrationResultPayload} from '../../services/interviews/calibration';
import {createInterview} from '../../services/interviews/createInterview';
import {CompleteInterviewResponse} from '../../types/interview';
import {CalibrationRouteState, interviewPath, ROUTES} from '../../utils/routes';
import {Camera, Microphone, Warning} from '../../icons';
import {CalibrationInstructionsModal} from './CalibrationInstructionsModal';

const WAVEFORM_BAR_COUNT = 80;

export const InterviewCalibration = () => {
  const {t, i18n} = useTranslation();
  const navigate = useNavigate(); const location = useLocation();
  const {interviewId: idParam} = useParams<{interviewId: string}>();
  const existingId = idParam ? Number.parseInt(idParam, 10) : null;
  const routeConfig = (location.state as CalibrationRouteState | null) ?? null;
  const media = useInterviewMedia();
  const calibration = useTechnicalCalibration(media.microphoneStream, media.cameraStream);
  const videoRef = useRef<HTMLVideoElement>(null); const processedMediaRef = useRef<Blob | null>(null);
  const [interview, setInterview] = useState<CompleteInterviewResponse | null>(null);
  // The calibration draft lives only in memory. A refresh, cancel, or navigation
  // away discards it and the user must repeat calibration -- intentional.
  const draftRef = useRef<CalibrationDraft | null>(null);
  const [result, setResult] = useState<'passed' | 'failed' | null>(null);
  const [failureReason, setFailureReason] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false); const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null); const [instructionsOpen, setInstructionsOpen] = useState(true);
  const [waveform, setWaveform] = useState<number[]>([]);
  const language: 'en' | 'es' = i18n.resolvedLanguage?.startsWith('es') ? 'es' : 'en';
  const missingConfig = existingId === null && !routeConfig;

  useEffect(() => {
    if (existingId === null || !Number.isFinite(existingId)) return;
    void getInterview(String(existingId), language).then(setInterview).catch(() => setError('load'));
  }, [existingId, language]);
  useEffect(() => {
    if (instructionsOpen || missingConfig) return;
    void Promise.all([media.startCamera(), media.startMicrophone()]);
  }, [instructionsOpen, media.startCamera, media.startMicrophone, missingConfig]);
  useEffect(() => { if (videoRef.current) videoRef.current.srcObject = media.cameraStream; }, [media.cameraStream]);
  useEffect(() => { setWaveform((current) => [...current.slice(-(WAVEFORM_BAR_COUNT - 1)), calibration.audioLevel]); }, [calibration.audioLevel]);

  useEffect(() => {
    const capture = calibration.media;
    if (!capture || processedMediaRef.current === capture.blob) return;
    processedMediaRef.current = capture.blob; setProcessing(true); setError(null);
    void processTemporaryCalibration(capture.blob, capture.durationMs, capture.metadata)
      .then((draft) => {
        // Replace any previous draft (a repeated calibration discards the old
        // one). Nothing is persisted server-side yet.
        draftRef.current = draft;
        setResult(draft.status === 'passed' ? 'passed' : 'failed');
        setFailureReason(draft.failureReason);
      })
      .catch(() => {
        draftRef.current = null;
        setError('processing');
      })
      .finally(() => setProcessing(false));
  }, [calibration.media]);

  const begin = useCallback(async () => {
    setError(null); setResult(null); setFailureReason(null);
    processedMediaRef.current = null; draftRef.current = null;
    try {
      await calibration.start();
    } catch {
      setError('start');
    }
  }, [calibration]);

  const continueToInterview = async () => {
    const draft = draftRef.current;
    if (!draft || draft.status !== 'passed' || result !== 'passed' || starting) return;
    setStarting(true); setError(null);
    try {
      let id = existingId;
      if (id === null) {
        if (!routeConfig) throw new Error('missing configuration');
        const created = await createInterview({clinical_case_id: String(routeConfig.clinicalCaseId), patient_response_language: routeConfig.patientResponseLanguage, patient_gender: routeConfig.gender || undefined, personality_id: routeConfig.personalityId || undefined});
        if (!created) throw new Error('missing interview');
        id = Number(created.id);
      }
      // Persist the calibration into the interview BEFORE starting it. If this
      // fails, the interview is not started and the draft is kept for retry.
      const payload: CalibrationResultPayload = {
        version: draft.calibrationVersion,
        status: draft.status,
        failureReason: draft.failureReason,
        profile: draft.profile,
        quality: draft.quality,
        personalBaseline: draft.personalBaseline,
      };
      await saveCalibrationResult(id, payload);
      await startInterview(id);
      navigate(interviewPath(id, 'session'), {replace: true, state: {justStarted: true}});
    } catch {
      setError('startInterview');
      setStarting(false);
    }
  };

  if (missingConfig) return <Navigate to={ROUTES.clinicalCases} replace />;
  if (interview?.status === 'completed') return <Navigate to={interviewPath(interview.id, 'review')} replace />;
  if (interview?.startTime) return <Navigate to={interviewPath(interview.id, 'session')} replace />;
  const devicesReady = media.cameraState === 'ready' && media.microphoneState === 'ready';
  const capturing = !['idle', 'complete', 'error'].includes(calibration.phase);
  const seconds = Math.ceil(calibration.remainingMs / 1_000);

  return <>
    <CalibrationInstructionsModal isOpen={instructionsOpen} onAccept={() => setInstructionsOpen(false)} onCancel={() => navigate(ROUTES.clinicalCases)} />
    {calibration.activeTarget && <div className="calibration-target-layer" aria-hidden="true"><span className="calibration-target" style={{left: `${calibration.activeTarget.x * 100}%`, top: `${calibration.activeTarget.y * 100}%`}} /></div>}
    <section className="calibration-page" aria-labelledby="calibration-title">
      <header className="calibration-header"><div><p className="calibration-eyebrow">{t('calibration.eyebrow')}</p><h1 id="calibration-title" className="calibration-title">{t('calibration.title')}</h1><p className="calibration-description">{t('calibration.instruction')}</p></div></header>
      <div className="calibration-grid">
        <article className="calibration-preview-card"><div className="calibration-preview">
          {media.cameraStream ? <video ref={videoRef} autoPlay muted playsInline aria-label={t('calibration.cameraPreview')} /> : <div className="calibration-preview__empty"><Camera color="currentColor" /><span>{t(`calibration.deviceStates.${media.cameraState}`)}</span></div>}
          {capturing && <><span className="calibration-recording-badge">{t('calibration.recording')}</span><span className="calibration-countdown">{seconds}</span></>}
        </div><div className="calibration-meter"><div className="voice-wave calibration-waveform" role="meter" aria-valuenow={Math.round(calibration.audioLevel * 100)}>{Array.from({length: WAVEFORM_BAR_COUNT}, (_, index) => <span key={index} style={{'--wave-level': waveform[index] ?? .025} as CSSProperties} />)}</div></div></article>
        <article className="calibration-panel">
          <div className="calibration-device-columns"><section><h2><Microphone color="currentColor" />{t('calibration.audio')}</h2><p>{media.microphoneState === 'ready' ? t('calibration.checks.microphoneActive') : t(`calibration.deviceStates.${media.microphoneState}`)}</p></section><section><h2><Camera color="currentColor" />{t('calibration.video')}</h2><p>{media.cameraState === 'ready' ? t('calibration.checks.videoActive') : t(`calibration.deviceStates.${media.cameraState}`)}</p></section></div>
          {capturing && <div className="calibration-result" role="status"><p>{t(`calibration.phases.${calibration.phase}`)}</p></div>}
          {processing && <div className="calibration-result" role="status"><p>{t('calibration.baselineProcessing')}</p></div>}
          {result && <div className={`calibration-result calibration-result--${result}`} role="status"><p>{t(result === 'passed' ? 'calibration.resultReadyDescription' : 'calibration.resultProblemDescription')}</p>{failureReason && <p className="calibration-result__warning">{t(`calibration.failures.${failureReason}`, {defaultValue: failureReason})}</p>}</div>}
          {error && <p className="calibration-message calibration-message--error" role="alert"><Warning color="currentColor" />{t(error === 'startInterview' ? 'clinicalSession.startFailed' : 'calibration.recordingError')}</p>}
          <footer className="calibration-actions"><button type="button" className="dialog-action dialog-action--secondary" onClick={() => navigate(ROUTES.clinicalCases)} disabled={capturing || processing || starting}>{t('common.cancel')}</button>{result === 'passed' ? <button type="button" className="dialog-action dialog-action--primary" onClick={() => void continueToInterview()} disabled={starting}>{t(starting ? 'calibration.saving' : 'calibration.startInterview')}</button> : <button type="button" className="dialog-action dialog-action--primary" onClick={() => void begin()} disabled={!devicesReady || capturing || processing}>{t(result === 'failed' ? 'calibration.repeat' : capturing ? 'calibration.calibrating' : 'calibration.startCalibration')}</button>}</footer>
        </article>
      </div>
    </section>
  </>;
};
