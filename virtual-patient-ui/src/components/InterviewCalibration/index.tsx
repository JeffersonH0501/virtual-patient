import {useCallback, useEffect, useRef, useState} from 'react';
import {Navigate, useLocation, useNavigate, useParams} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {useInterviewMedia} from '../../contexts/interviewMedia';
import {CalibrationStage, useTechnicalCalibration} from '../../hooks/useTechnicalCalibration';
import {getInterview, processCalibrationStage, saveCalibrationResult, startInterview} from '../../services/interviews';
import {CalibrationStageResult, CalibrationResultPayload} from '../../services/interviews/calibration';
import {createInterview} from '../../services/interviews/createInterview';
import {CompleteInterviewResponse, PersonalBaseline} from '../../types/interview';
import {CalibrationRouteState, interviewPath, ROUTES} from '../../utils/routes';
import {CalibrationActiveStep, CalibrationCheckpoint, CalibrationPreparation, CalibrationProcessing} from './CalibrationWizard';

const STAGES: CalibrationStage[] = ['voice', 'gaze', 'camera'];
type View = 'preparation' | 'checkpoint' | 'capturing' | 'processing' | 'stage-result';

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
  const resultsRef = useRef<Partial<Record<CalibrationStage, CalibrationStageResult>>>({});
  const [interview, setInterview] = useState<CompleteInterviewResponse | null>(null);
  const [view, setView] = useState<View>('preparation');
  const [stageIndex, setStageIndex] = useState(0);
  const [stageResult, setStageResult] = useState<CalibrationStageResult | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const language: 'en' | 'es' = i18n.resolvedLanguage?.startsWith('es') ? 'es' : 'en';
  const stage = STAGES[stageIndex];
  const missingConfig = existingId === null && !routeConfig;
  const devicesReady = media.cameraState === 'ready' && media.microphoneState === 'ready';

  useEffect(() => {
    if (existingId === null || !Number.isFinite(existingId)) return;
    void getInterview(String(existingId), language).then(setInterview).catch(() => setError('load'));
  }, [existingId, language]);
  useEffect(() => {
    if (!missingConfig) void Promise.all([media.startCamera(), media.startMicrophone()]);
  }, [media.startCamera, media.startMicrophone, missingConfig]);
  useEffect(() => {
 titleRef.current?.focus({preventScroll: true});
}, [view, stageIndex]);

  useEffect(() => {
    const capture = calibration.media;
    if (!capture || processedMediaRef.current === capture.blob) return;
    processedMediaRef.current = capture.blob;
    setView('processing');
    void processCalibrationStage(capture.stage, capture.blob, capture.durationMs, capture.metadata)
      .then((result) => {
        setStageResult(result);
        if (result.status === 'passed') resultsRef.current[result.stage] = result;
        setView('stage-result');
      })
      .catch(() => {
        setStageResult({stage: capture.stage, status: 'failed', failureReason: 'processing_failed', result: null});
        setView('stage-result');
      });
  }, [calibration.media]);

  useEffect(() => {
    if (calibration.phase === 'error' && view === 'capturing') {
      setStageResult({stage, status: 'failed', failureReason: 'processing_failed', result: null});
      setView('stage-result');
    }
  }, [calibration.phase, stage, view]);

  const beginStage = useCallback(async () => {
    setStageResult(null);
    setError(null);
    processedMediaRef.current = null;
    calibration.reset();
    const gazeProfile = resultsRef.current.gaze?.result?.profile as Record<string, unknown> | undefined;
    const metadata = stage === 'camera' ? {affineMatrix: gazeProfile?.affineMatrix} : {};
    setView('capturing');
    await calibration.start(stage, metadata);
  }, [calibration, stage]);

  const nextCheckpoint = () => {
    if (stageIndex < STAGES.length - 1) {
      calibration.reset();
      setStageIndex((current) => current + 1);
      setStageResult(null);
      setView('checkpoint');
    }
  };

  const buildPayload = (): CalibrationResultPayload | null => {
    const gaze = resultsRef.current.gaze?.result;
    const camera = resultsRef.current.camera?.result;
    const voice = resultsRef.current.voice?.result;
    if (!gaze || !camera || !voice) return null;
    const gazeProfile = gaze.profile as Record<string, unknown>;
    const cameraCenter = camera.cameraReferenceCenter as number[];
    const neutralHead = camera.neutralHead as Record<string, number>;
    const personalBaseline: PersonalBaseline = {
      baselineF0Semitones: voice.baselineF0Semitones as number,
      baselineLoudness: voice.baselineLoudness as number,
      neutralHeadYaw: neutralHead.neutralHeadYaw,
      neutralHeadPitch: neutralHead.neutralHeadPitch,
      neutralHeadRoll: neutralHead.neutralHeadRoll,
      neutralGazeYaw: cameraCenter[0],
      neutralGazePitch: cameraCenter[1],
    };
    return {
      version: 'multimodal_calibration_checkpoints_v2',
      status: 'passed', failureReason: null,
      profile: {...gazeProfile, cameraReferenceCenter: cameraCenter, personalBaseline},
      quality: {...(gaze.quality as object), ...(camera.quality as object), validSpeechDurationMs: voice.voicedDurationMs, clippingDetected: voice.clippingDetected},
      personalBaseline,
    };
  };

  const continueToInterview = async () => {
    const payload = buildPayload();
    if (!payload || starting) return;
    setStarting(true); setError(null);
    try {
      let id = existingId;
      if (id === null) {
        if (!routeConfig) throw new Error('Missing interview configuration');
        const created = await createInterview({clinical_case_id: String(routeConfig.clinicalCaseId), patient_response_language: routeConfig.patientResponseLanguage, patient_gender: routeConfig.gender || undefined, personality_id: routeConfig.personalityId || undefined});
        if (!created) throw new Error('Interview creation returned no result');
        id = Number(created.id);
      }
      await saveCalibrationResult(id, payload);
      await startInterview(id);
      navigate(interviewPath(id, 'session'), {replace: true, state: {justStarted: true}});
    } catch {
 setError('startInterview'); setStarting(false);
}
  };

  if (missingConfig) return <Navigate to={ROUTES.clinicalCases} replace />;
  if (interview?.status === 'completed') return <Navigate to={interviewPath(interview.id, 'review')} replace />;
  if (interview?.startTime) return <Navigate to={interviewPath(interview.id, 'session')} replace />;

  return (
    <section className="calibration-experience">
      {calibration.activeTarget && <div className="calibration-target-layer" aria-hidden="true"><span className="calibration-target" style={{left: `${calibration.activeTarget.x * 100}%`, top: `${calibration.activeTarget.y * 100}%`}} /></div>}
      {view === 'preparation' && <CalibrationPreparation cameraStream={media.cameraStream} cameraState={media.cameraState} microphoneState={media.microphoneState} audioLevel={calibration.audioLevel} devicesReady={devicesReady} onStart={() => setView('checkpoint')} onBack={() => navigate(ROUTES.clinicalCases)} onRetryDevices={() => void Promise.all([media.startCamera(), media.startMicrophone()])} />}
      {view === 'checkpoint' && <CalibrationCheckpoint stage={stage} activeStep={stageIndex + 1} onStart={() => void beginStage()} titleRef={titleRef} />}
      {view === 'capturing' && <CalibrationActiveStep phase={calibration.phase} seconds={Math.ceil(calibration.remainingMs / 1000)} audioLevel={calibration.audioLevel} titleRef={titleRef} />}
      {view === 'processing' && <CalibrationProcessing stage={stage} activeStep={stageIndex + 1} titleRef={titleRef} />}
      {view === 'stage-result' && stageResult && <CalibrationCheckpoint stage={stage} activeStep={stageIndex + 1} passed={stageResult.status === 'passed'} failureReason={stageResult.failureReason} onStart={() => void beginStage()} onContinue={stage === 'camera' ? () => void continueToInterview() : nextCheckpoint} busy={starting} error={error === 'startInterview'} titleRef={titleRef} />}
    </section>
  );
};
