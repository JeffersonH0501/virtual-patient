import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Navigate, useLocation, useNavigate, useParams} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {useInterviewMedia} from '../../contexts/interviewMedia';
import {useTechnicalCalibration} from '../../hooks/useTechnicalCalibration';
import {
  getInterview,
  processTemporaryCalibration,
  saveCalibrationResult,
  startInterview,
} from '../../services/interviews';
import {CalibrationDraft, CalibrationResultPayload} from '../../services/interviews/calibration';
import {createInterview} from '../../services/interviews/createInterview';
import {CompleteInterviewResponse} from '../../types/interview';
import {CalibrationRouteState, interviewPath, ROUTES} from '../../utils/routes';
import {
  CalibrationActiveStep,
  CalibrationPreparation,
  CalibrationProcessing,
  CalibrationResult,
} from './CalibrationWizard';

export const InterviewCalibration = () => {
  const {i18n} = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const {interviewId: idParam} = useParams<{interviewId: string}>();
  const existingId = idParam ? Number.parseInt(idParam, 10) : null;
  const routeConfig = (location.state as CalibrationRouteState | null) ?? null;
  const media = useInterviewMedia();
  const calibration = useTechnicalCalibration(media.microphoneStream, media.cameraStream);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const processedMediaRef = useRef<Blob | null>(null);
  const draftRef = useRef<CalibrationDraft | null>(null);
  const [interview, setInterview] = useState<CompleteInterviewResponse | null>(null);
  const [result, setResult] = useState<'passed' | 'failed' | null>(null);
  const [failureReason, setFailureReason] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const language: 'en' | 'es' = i18n.resolvedLanguage?.startsWith('es') ? 'es' : 'en';
  const missingConfig = existingId === null && !routeConfig;
  const devicesReady = media.cameraState === 'ready' && media.microphoneState === 'ready';
  const capturing = !['idle', 'complete', 'error'].includes(calibration.phase);
  const seconds = Math.ceil(calibration.remainingMs / 1_000);
  const presentationState = useMemo(() => {
    if (result) return result;
    if (processing || calibration.phase === 'complete') return 'processing';
    if (capturing) return calibration.phase;
    return 'preparation';
  }, [calibration.phase, capturing, processing, result]);

  useEffect(() => {
    if (existingId === null || !Number.isFinite(existingId)) return;
    void getInterview(String(existingId), language)
      .then(setInterview)
      .catch(() => setError('load'));
  }, [existingId, language]);

  useEffect(() => {
    if (missingConfig) return;
    void Promise.all([media.startCamera(), media.startMicrophone()]);
  }, [media.startCamera, media.startMicrophone, missingConfig]);

  useEffect(() => {
    titleRef.current?.focus({preventScroll: true});
  }, [presentationState]);

  useEffect(() => {
    if (calibration.phase !== 'error' || result) return;
    setFailureReason('processing_failed');
    setResult('failed');
  }, [calibration.phase, result]);

  useEffect(() => {
    const capture = calibration.media;
    if (!capture || processedMediaRef.current === capture.blob) return;
    processedMediaRef.current = capture.blob;
    setProcessing(true);
    setError(null);
    void processTemporaryCalibration(capture.blob, capture.durationMs, capture.metadata)
      .then((draft) => {
        draftRef.current = draft;
        setResult(draft.status === 'passed' ? 'passed' : 'failed');
        setFailureReason(draft.failureReason);
      })
      .catch(() => {
        draftRef.current = null;
        setFailureReason('processing_failed');
        setResult('failed');
      })
      .finally(() => setProcessing(false));
  }, [calibration.media]);

  const begin = useCallback(async () => {
    setError(null);
    setResult(null);
    setFailureReason(null);
    processedMediaRef.current = null;
    draftRef.current = null;
    calibration.reset();
    try {
      await calibration.start();
    } catch {
      setFailureReason('processing_failed');
      setResult('failed');
    }
  }, [calibration]);

  const retryDevices = useCallback(() => {
    void Promise.all([media.startCamera(), media.startMicrophone()]);
  }, [media.startCamera, media.startMicrophone]);

  const continueToInterview = async () => {
    const draft = draftRef.current;
    if (!draft || draft.status !== 'passed' || result !== 'passed' || starting) return;
    setStarting(true);
    setError(null);
    try {
      let id = existingId;
      if (id === null) {
        if (!routeConfig) throw new Error('Missing interview configuration');
        const created = await createInterview({
          clinical_case_id: String(routeConfig.clinicalCaseId),
          patient_response_language: routeConfig.patientResponseLanguage,
          patient_gender: routeConfig.gender || undefined,
          personality_id: routeConfig.personalityId || undefined,
        });
        if (!created) throw new Error('Interview creation returned no result');
        id = Number(created.id);
      }
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
  if (interview?.status === 'completed') {
    return <Navigate to={interviewPath(interview.id, 'review')} replace />;
  }
  if (interview?.startTime) return <Navigate to={interviewPath(interview.id, 'session')} replace />;

  return (
    <section className="calibration-experience">
      {calibration.activeTarget && (
        <div className="calibration-target-layer" aria-hidden="true">
          <span
            className="calibration-target"
            style={{
              left: `${calibration.activeTarget.x * 100}%`,
              top: `${calibration.activeTarget.y * 100}%`,
            }}
          />
        </div>
      )}
      {presentationState === 'preparation' && (
        <CalibrationPreparation
          cameraStream={media.cameraStream}
          cameraState={media.cameraState}
          microphoneState={media.microphoneState}
          audioLevel={calibration.audioLevel}
          devicesReady={devicesReady}
          onStart={() => void begin()}
          onBack={() => navigate(ROUTES.clinicalCases)}
          onRetryDevices={retryDevices}
          titleRef={titleRef}
        />
      )}
      {capturing && (
        <CalibrationActiveStep
          phase={calibration.phase}
          seconds={seconds}
          targetOrder={calibration.activeTarget?.order ?? 1}
          cameraStream={media.cameraStream}
          cameraState={media.cameraState}
          audioLevel={calibration.audioLevel}
          titleRef={titleRef}
        />
      )}
      {presentationState === 'processing' && <CalibrationProcessing titleRef={titleRef} />}
      {(presentationState === 'passed' || presentationState === 'failed') && (
        <CalibrationResult
          passed={presentationState === 'passed'}
          failureReason={failureReason}
          busy={starting}
          error={error === 'startInterview'}
          onContinue={() => void continueToInterview()}
          onRetry={() => void begin()}
          onBack={() => navigate(ROUTES.clinicalCases)}
          titleRef={titleRef}
        />
      )}
    </section>
  );
};
