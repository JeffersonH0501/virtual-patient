import {useCallback, useEffect, useLayoutEffect, useRef, useState} from 'react';
import {Navigate, useLocation, useNavigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {X} from 'lucide-react';
import {Button} from '../common/Button';
import {InterviewContentLoading} from '../ClinicalChat/InterviewContentLoading';
import {Dialog} from '../common/Dialog';
import {useInterviewMedia} from '../../contexts/interviewMedia';
import {useUser} from '../../hooks/useUser';
import {CalibrationStage, GuidedCheckEnvironment, readGeometry, useTechnicalCalibration} from '../../hooks/useTechnicalCalibration';
import {discardCalibrationDraft, discardResumeCalibration, getInterview, processCalibrationStage, saveCalibrationResult, warmUpCalibration} from '../../services/interviews';
import {CalibrationStageResult, CalibrationResultPayload, GuidedCheckDiagnostics, processNonverbalTest} from '../../services/interviews/calibration';
import {createInterview} from '../../services/interviews/createInterview';
import {CompleteInterviewResponse, PersonalBaseline} from '../../types/interview';
import {CalibrationRouteState, InterviewResumeState, interviewPath, ROUTES} from '../../utils/routes';
import {CalibrationActiveStep, CalibrationCheckpoint, CalibrationPreparation, CalibrationProcessing} from './CalibrationWizard';
import {GazeTest} from './GazeTest';

const STAGES: CalibrationStage[] = ['gaze', 'camera'];
type View = 'preparation' | 'checkpoint' | 'capturing' | 'processing' | 'stage-result' | 'live-gaze';

export const InterviewCalibration = () => {
  const {i18n, t} = useTranslation();
  const {user} = useUser();
  const [exitOpen, setExitOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as CalibrationRouteState | {draftInterviewId: number; resume?: InterviewResumeState} | null;
  const resume = state && 'draftInterviewId' in state ? state.resume : undefined;
  const existingId = state && 'draftInterviewId' in state ? state.draftInterviewId : null;
  const routeConfig = state && 'clinicalCaseId' in state ? state : null;
  const nonverbalTest = routeConfig?.calibrationTest === true && user?.role === 'superuser';
  const gazeTest = routeConfig?.gazeTest === true && user?.role === 'superuser';
  const calibrationTest = nonverbalTest || gazeTest;
  const media = useInterviewMedia();
  const calibration = useTechnicalCalibration(media.microphoneStream, media.cameraStream);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const draftIdRef = useRef(existingId);
  const draftRequestIdRef = useRef<string | null>(null);
  const testAttemptRef = useRef<string | null>(null);
  const [testVideoUrl, setTestVideoUrl] = useState<string | null>(null);
  useEffect(() => () => { if (testVideoUrl) URL.revokeObjectURL(testVideoUrl); }, [testVideoUrl]);
  const calibrationSavedRef = useRef(false);
  const mountedRef = useRef(false);
  const handedOffRef = useRef(false);
  const exitConfirmedRef = useRef(false);
  const [exiting, setExiting] = useState(false);
  const discardDraft = useCallback(async () => {
    if (calibrationTest) return;
    const identifier = draftIdRef.current;
    if (identifier === null || handedOffRef.current) return;
    if (resume) await discardResumeCalibration(identifier, resume.resumeAttemptId);
    else await discardCalibrationDraft(identifier);
    if (draftIdRef.current === identifier) draftIdRef.current = null;
  }, [resume, calibrationTest]);
  useEffect(() => {
    mountedRef.current = true;
    const discardOnLeave = () => {
 if (!resume) void discardDraft().catch(() => undefined);
};
    window.addEventListener('pagehide', discardOnLeave);
    return () => {
      mountedRef.current = false;
      window.removeEventListener('pagehide', discardOnLeave);
      // A Strict Mode effect replay remounts before this microtask runs.
      queueMicrotask(() => {
 if (!mountedRef.current) discardOnLeave();
});
    };
  }, [discardDraft, resume]);
  const processedMediaRef = useRef<Blob | null>(null);
  const resultsRef = useRef<Partial<Record<CalibrationStage, CalibrationStageResult>>>({});
  const [interview, setInterview] = useState<CompleteInterviewResponse | null>(null);
  const [view, setView] = useState<View>('preparation');
  const [stage, setStage] = useState<CalibrationStage>('unified');
  const [stageResult, setStageResult] = useState<CalibrationStageResult | null>(null);
  const [guidedEnvironment, setGuidedEnvironment] = useState<GuidedCheckEnvironment>({deviceType: 'laptop', cameraPosition: 'top'});
  const [guidedDiagnostics, setGuidedDiagnostics] = useState<GuidedCheckDiagnostics | null>(null);
  const [starting, setStarting] = useState(false);
  const [captureStarting, setCaptureStarting] = useState(false);
  const captureStartingRef = useRef(false);
  const startAttemptRef = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [uploadAttempt, setUploadAttempt] = useState(0);
  const language: 'en' | 'es' = i18n.resolvedLanguage?.startsWith('es') ? 'es' : 'en';
  const {phase} = calibration;
  const displayPhase = phase === 'idle' && stage === 'camera' ? 'camera_reference' : phase;
  const activeCapture = displayPhase !== 'idle' && displayPhase !== 'complete' && displayPhase !== 'error';
  const missingConfig = existingId === null && !routeConfig;
  const devicesReady = media.cameraState === 'ready' && media.microphoneState === 'ready';
  useLayoutEffect(() => {
    if (phase === 'gaze_targets' && calibration.activeTarget) calibration.confirmPresentation?.(calibration.activeTarget.order);
    else if (phase === 'camera_reference') calibration.confirmPresentation?.(null);
    else if (phase === 'guided_check' && calibration.activeCheck) calibration.confirmPresentation?.(calibration.activeCheck);
  }, [phase, calibration.activeTarget, calibration.activeCheck, calibration.confirmPresentation]);


  useEffect(() => {
    if (existingId === null || !Number.isFinite(existingId)) return;
    let current = true;
    void getInterview(String(existingId), language, AbortSignal.timeout(30_000))
      .then((loaded) => {
 if (current) setInterview(loaded);
})
      .catch(() => {
 if (current) setError('load');
});
    return () => {
 current = false;
};
  }, [existingId, language, loadAttempt]);
  useEffect(() => {
    if (!missingConfig) void Promise.all([media.startCamera(), media.startMicrophone()]);
  }, [media.startCamera, media.startMicrophone, missingConfig]);
  useEffect(() => {
 titleRef.current?.focus({preventScroll: true});
}, [view, activeCapture]);

  useEffect(() => {
    const capture = calibration.media;
    const draftId = draftIdRef.current;
    if (!capture || (!calibrationTest && draftId === null) || processedMediaRef.current === capture.blob) return;
    processedMediaRef.current = capture.blob;
    setView('processing');
    if (calibrationTest && capture.stage === 'guided') setTestVideoUrl(URL.createObjectURL(capture.blob));
    const args = [capture.stage, draftId!, capture.blob, capture.durationMs, capture.metadata] as const;
    const request = calibrationTest
      ? processNonverbalTest(capture.stage, testAttemptRef.current!, capture.blob, capture.durationMs, capture.metadata)
      : resume ? processCalibrationStage(...args, resume.resumeAttemptId) : processCalibrationStage(...args);
    void request
      .then((result) => {
        if (!mountedRef.current) return;
        if (capture.stage === 'guided') {
          setGuidedDiagnostics((result.result?.guidedChecks as GuidedCheckDiagnostics | undefined) ?? null);
          setStageResult(result);
        } else if (capture.stage === 'unified') {
          setGuidedDiagnostics((result.result?.guidedChecks as GuidedCheckDiagnostics | undefined) ?? null);
          const checkpoints = result.result?.checkpoints as Partial<Record<CalibrationStage, CalibrationStageResult>> | undefined;
          for (const checkpoint of STAGES) {
            if (checkpoints?.[checkpoint]?.status === 'passed') resultsRef.current[checkpoint] = checkpoints[checkpoint];
          }
          const failed = result.result?.failedStage as 'gaze' | 'camera' | undefined;
          const display = checkpoints?.[failed ?? 'camera'] ?? {...result, stage: 'gaze'};
          const gazeQuality = checkpoints?.gaze?.result?.quality as Record<string, unknown> | undefined;
          setStageResult(calibrationTest && gazeQuality ? {...display, result: {...display.result,
            quality: {...(display.result?.quality as Record<string, unknown> ?? {}), ...gazeQuality},
            experimentalQualityBypass: result.result?.experimentalQualityBypass ?? display.result?.experimentalQualityBypass}} : display);
          setStage(failed === 'camera' && result.failureReason !== 'geometry' ? 'camera' : 'unified');
        } else {
          setStageResult(result);
          if (result.status === 'passed') resultsRef.current[result.stage] = result;
          if (result.failureReason === 'geometry') {
 resultsRef.current = {}; setStage('unified');
}
        }
        setView('stage-result');
      })
      .catch((failure: unknown) => {
        if (!mountedRef.current) return;
        if (failure instanceof Error && 'status' in failure && [404, 410].includes(Number(failure.status))) {
          draftIdRef.current = null; draftRequestIdRef.current = null;
          resultsRef.current = {}; calibrationSavedRef.current = false; setStage('unified');
          setStageResult({stage: 'gaze', status: 'failed', failureReason: 'draft_expired', result: null});
          setView('stage-result');
          return;
        }
        const retryUpload = failure instanceof TypeError ||
          (failure instanceof DOMException && failure.name === 'TimeoutError') ||
          (failure instanceof Error && 'status' in failure && [409, 503].includes(Number(failure.status)));
        const tooLarge = failure instanceof Error && 'status' in failure && Number(failure.status) === 413;
        if (capture.stage === 'guided' && failure instanceof Error && 'status' in failure && Number(failure.status) === 422) {
          resultsRef.current = {}; setStage('unified');
          setStageResult({stage: 'gaze', status: 'failed', failureReason: 'geometry', result: null});
          setView('stage-result');
          return;
        }
        setStageResult({stage: capture.stage, status: 'failed', failureReason: tooLarge ? 'upload_too_large' : retryUpload ? 'upload_failed' : 'processing_failed', result: null});
        setView('stage-result');
      });
  }, [calibration.media, calibrationTest, resume, uploadAttempt]);

  useEffect(() => {
    if (calibration.phase === 'error' && view === 'capturing') {
      setStageResult({stage, status: 'failed', failureReason: calibration.failureReason ?? 'recording_failed', result: null});
      setView('stage-result');
    }
  }, [calibration.phase, stage, view]);

  const beginStage = useCallback(async (captureStage: CalibrationStage = stage, environment = guidedEnvironment) => {
    if (captureStartingRef.current || starting) return;
    if (draftIdRef.current === null && !routeConfig) {
 navigate(ROUTES.clinicalCases, {replace: true}); return;
}
    const attempt = ++startAttemptRef.current;
    captureStartingRef.current = true;
    setCaptureStarting(true);
    setError(null);
    try {
      if (calibrationTest) {
        testAttemptRef.current ??= crypto.randomUUID();
      } else if (draftIdRef.current === null) {
        if (!routeConfig) throw new Error('Missing interview configuration');
        draftRequestIdRef.current ??= crypto.randomUUID();
        const created = await createInterview({clinical_case_id: String(routeConfig.clinicalCaseId), patient_response_language: routeConfig.patientResponseLanguage, patient_gender: routeConfig.gender || undefined, personality_id: routeConfig.personalityId || undefined, draft_request_id: draftRequestIdRef.current});
        if (!created) throw new Error('Interview creation returned no result');
        if (!mountedRef.current || exitConfirmedRef.current) {
          void discardCalibrationDraft(Number(created.id)).catch(() => undefined);
          return;
        }
        draftIdRef.current = Number(created.id);
        if (attempt !== startAttemptRef.current) return;
      }
      if (!mountedRef.current || attempt !== startAttemptRef.current) return;
      setStage(captureStage);
      setStageResult(null);
      processedMediaRef.current = null;
      if (captureStage === 'unified') {
        resultsRef.current = {}; setGuidedDiagnostics(null); setTestVideoUrl(null);
      }
      calibrationSavedRef.current = false;
      const gazeProfile = resultsRef.current.gaze?.result?.profile as Record<string, unknown> | undefined;
      const metadata = captureStage === 'guided' ? {
        guidedEnvironment: environment,
        nonverbalOnly: nonverbalTest,
        attestations: nonverbalTest ? {} : {gaze: resultsRef.current.gaze?.attestation, camera: resultsRef.current.camera?.attestation},
      } : captureStage === 'camera' ? {
        affineMatrix: gazeProfile?.affineMatrix, expectedGeometry: gazeProfile?.captureGeometry,
        gazeSource: gazeProfile?.gazeSource, attestations: {gaze: resultsRef.current.gaze?.attestation},
      } : {};
      setView('capturing');
      await calibration.start(captureStage, metadata);
    } catch {
      if (!mountedRef.current || attempt !== startAttemptRef.current) return;
      setStageResult({stage: captureStage, status: 'failed', failureReason: !calibrationTest && draftIdRef.current === null ? 'draft_create_failed' : 'recording_failed', result: null});
      setView('stage-result');
    } finally {
      if (attempt === startAttemptRef.current) {
        captureStartingRef.current = false;
        if (mountedRef.current) setCaptureStarting(false);
      }
    }
  }, [calibration, navigate, routeConfig, stage, starting, guidedEnvironment, calibrationTest, nonverbalTest]);

  const buildPayload = (): CalibrationResultPayload | null => {
    const gaze = resultsRef.current.gaze?.result;
    const camera = resultsRef.current.camera?.result;
    if (!gaze || !camera) return null;
    const attestations: Record<string, string> = {};
    for (const checkpoint of STAGES) {
      const attestation = resultsRef.current[checkpoint]?.attestation;
      if (!attestation) return null;
      attestations[checkpoint] = attestation;
    }
    const gazeProfile = gaze.profile as Record<string, unknown>;
    const cameraCenter = camera.cameraReferenceCenter as number[];
    const neutralHead = camera.neutralHead as Record<string, number>;
    const personalBaseline: PersonalBaseline = {
      neutralHeadYaw: neutralHead.neutralHeadYaw,
      neutralHeadPitch: neutralHead.neutralHeadPitch,
      neutralHeadRoll: neutralHead.neutralHeadRoll,
      neutralGazeYaw: cameraCenter[0],
      neutralGazePitch: cameraCenter[1],
    };
    return {
      version: 'multimodal_calibration_presented_intervals_v4',
      status: 'passed', failureReason: null,
      profile: {...gazeProfile, cameraReferenceCenter: cameraCenter, cameraEyeReference:camera.cameraEyeReference, personalBaseline},
      quality: {...(gaze.quality as object), ...(camera.quality as object)},
      personalBaseline,
      attestations,
    };
  };

  const continueToInterview = async () => {
    const payload = buildPayload();
    if (!payload || starting) return;
    setStarting(true); setError(null);
    try {
      const id = draftIdRef.current;
      if (id === null) throw new Error('Missing calibration draft');
      if (!calibrationSavedRef.current) {
        if (resume) await saveCalibrationResult(id, payload, resume.resumeAttemptId);
        else await saveCalibrationResult(id, payload);
        calibrationSavedRef.current = true;
      }
      handedOffRef.current = true;
      media.bindInterview(String(id));
      navigate(interviewPath(id, 'session'), {replace: true, state: {justStarted: true, ...(resume ? {resume} : {})}});
    } catch (failure) {
      if (failure instanceof Error && 'status' in failure && [404, 410].includes(Number(failure.status))) {
        draftIdRef.current = null; draftRequestIdRef.current = null;
        resultsRef.current = {};
        calibration.reset();
        setStageResult(null);
        setStage('unified');
        setView('checkpoint');
        setError('expired');
      } else {
        setError('startInterview');
      }
      setStarting(false);
    }
  };

  const leaveCalibration = async () => {
    if (exiting || starting) return;
    setExiting(true); setError(null); exitConfirmedRef.current = true;
    try {
      await discardDraft();
      navigate(resume && existingId !== null ? interviewPath(existingId, 'session') : ROUTES.clinicalCases, {replace: true});
    } catch {
      exitConfirmedRef.current = false;
      setExiting(false); setExitOpen(true); setError('discard');
    }
  };

  if (missingConfig) return <Navigate to={ROUTES.clinicalCases} replace />;
  if (interview?.status === 'completed') return <Navigate to={interviewPath(interview.id, 'review')} replace />;
  if (interview?.startTime && (!resume || interview.status !== 'in_progress')) return <Navigate to={interviewPath(interview.id, 'session')} replace />;

  return (
    <section className="calibration-experience relative">
      <button
        type="button"
        className="absolute right-layout top-layout z-10 rounded p-2 text-white hover:text-neutral-300"
        aria-label={t('calibration.exitTitle')}
        disabled={starting || exiting}
        onClick={() => {
          if (view === 'capturing' || captureStartingRef.current) {
            startAttemptRef.current += 1;
            captureStartingRef.current = false;
            setCaptureStarting(false);
            calibration.cancel('capture_interrupted');
            setStageResult({stage, status: 'failed', failureReason: 'capture_interrupted', result: null});
            setView('stage-result');
          }
          setExitOpen(true);
        }}
      >
        <X aria-hidden="true" className="h-7 w-7" />
      </button>
      <Dialog
        title={t('calibration.exitTitle')}
        open={exitOpen}
        busy={exiting}
        onClose={() => setExitOpen(false)}
        hasDismissAction
        actions={
          <>
            <Button variant="secondary" disabled={exiting} onClick={() => setExitOpen(false)}>{t('common.cancel')}</Button>
            <Button disabled={exiting} onClick={() => void leaveCalibration()}>{t('calibration.exitTitle')}</Button>
          </>
        }
      >
        <p className="dialog-copy">{t('calibration.exitDescription')}</p>
        {error === 'discard' && <p role="alert">{t('calibration.discardError')}</p>}
      </Dialog>
      {error === 'load' && <div role="alert" className="calibration-friendly-alert">
        <p>{t('calibration.draftLoadError')}</p>
        <Button onClick={() => {
 setError(null); setLoadAttempt((attempt) => attempt + 1);
}}>{t('calibration.retryLoad')}</Button>
      </div>}
      {existingId !== null && !interview && error !== 'load' && <InterviewContentLoading />}
      {error === 'expired' && <p role="alert" className="calibration-friendly-alert">{t('calibration.checkpointsExpired')}</p>}
      {(calibration.activeTarget || calibration.activeCheck === 'gaze_turn') && <div className="calibration-target-layer" aria-hidden="true"><span className="calibration-target" style={{left: `${(calibration.activeTarget?.x ?? .5) * 100}%`, top: `${(calibration.activeTarget?.y ?? .5) * 100}%`}} /></div>}
      {view === 'preparation' && (existingId === null || interview) && (
        <CalibrationPreparation
          audioLevel={calibration.audioLevel}
          cameraStream={media.cameraStream}
          cameraState={media.cameraState}
          microphoneState={media.microphoneState}

          devicesReady={devicesReady && !captureStarting}
          guidedOnly={nonverbalTest}
          cameraDeviceId={media.cameraDeviceId}
          microphoneDeviceId={media.microphoneDeviceId}
          onSelectCamera={media.startCamera}
          onSelectMicrophone={media.startMicrophone}
          onStart={() => {
 void warmUpCalibration().catch(() => undefined); void beginStage('unified');
}}
          onStartGuided={nonverbalTest ? (environment) => {
 setGuidedEnvironment(environment); void warmUpCalibration().catch(() => undefined); void beginStage('guided', environment);
} : undefined}
          onBack={() => void leaveCalibration()}
          onRetryCamera={() => void media.startCamera()}
          onRetryMicrophone={() => void media.startMicrophone()}
        />
      )}
      {view === 'checkpoint' && <CalibrationCheckpoint stage={stageResult?.stage === 'camera' ? 'camera' : 'gaze'} onStart={() => void beginStage()} busy={captureStarting} titleRef={titleRef} />}
      {view === 'capturing' && activeCapture && <CalibrationActiveStep phase={displayPhase} activeCheck={calibration.activeCheck} waitingForStep={calibration.waitingForStep} onStartStep={calibration.startGuidedStep} remainingMs={calibration.remainingMs} seconds={Math.max(1, Math.ceil(calibration.remainingMs / 1000))} titleRef={titleRef} />}
      {(view === 'processing' || (view === 'capturing' && phase === 'complete')) && <CalibrationProcessing titleRef={titleRef} />}
      {view === 'stage-result' && stageResult && <CalibrationCheckpoint experimentalOverride={stageResult.result?.experimentalQualityBypass === true} guidedDiagnostics={guidedDiagnostics} guidedVideoUrl={calibrationTest ? testVideoUrl : null} stage={stageResult?.stage === 'camera' ? 'camera' : 'gaze'} diagnostics={stageResult.result?.quality} passed={stageResult.status === 'passed'} failureReason={stageResult.failureReason} onStart={() => {
        if (stageResult.failureReason === 'upload_failed') {
          processedMediaRef.current = null;
          setUploadAttempt((attempt) => attempt + 1);
        } else {
          void beginStage();
        }
      }} onContinue={() => {
        if (gazeTest) setView('live-gaze');
        else void (nonverbalTest ? guidedDiagnostics ? leaveCalibration() : beginStage('guided') : continueToInterview());
      }} continueLabel={gazeTest ? t('calibration.gazeTest.start') : nonverbalTest ? t(guidedDiagnostics ? 'calibration.finishTest' : 'calibration.guided.startTests') : undefined} onRestart={() => void beginStage('unified')} busy={starting || captureStarting} error={error === 'startInterview'} titleRef={titleRef} />}
      {view === 'live-gaze' && media.cameraStream && testAttemptRef.current && resultsRef.current.gaze?.attestation && resultsRef.current.camera?.attestation && <GazeTest
        stream={media.cameraStream} attemptId={testAttemptRef.current} gazeToken={resultsRef.current.gaze.attestation} cameraToken={resultsRef.current.camera.attestation}
        geometry={(resultsRef.current.gaze.result?.profile as {captureGeometry: ReturnType<typeof readGeometry>}).captureGeometry}
        onRestart={() => void beginStage('unified')} onExit={() => void leaveCalibration()} />}
    </section>
  );
};
