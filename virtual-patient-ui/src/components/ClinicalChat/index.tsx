import {FC, useCallback, useEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {useTranslation} from 'react-i18next';
import {Navigate, useLocation, useNavigate, useOutletContext, useParams} from 'react-router-dom';
import {PatientProfile} from './PatientProfile';
import {Modal} from '../common';
import {ClinicalHypotheses} from './ClinicalHypotheses';
import {WelcomeModal} from './WelcomeModal';
import {TeacherFeedbackSection} from './TeacherFeedbackSection';
import {CallStage} from './CallStage';
import {CallToolbar} from './CallToolbar';
import {ConversationTranscript} from './ConversationTranscript';
import {InterviewRecap} from './InterviewRecap';
import {ActiveSimulationLayout, SimulationResultsLayout} from './InterviewLayouts';
import {createSummary, interruptInterview, sendMessage, startInterview} from '../../services/interviews';
import {getInterview} from '../../services/interviews/getInterview';
import {getInterviewRecap, reprocessInterviewRecording} from '../../services/recordings';
import {getSessionNote, updateSessionNote} from '../../services/sessionNote';
import {CompleteInterviewResponse} from '../../types/interview';
import {Patient} from '../../types/patient';
import {Message} from '../../types/message';
import {InterviewEvaluationResponse} from '../../types/evaluation';
import {EvaluationResultsPanel} from '../Evaluation';
import {getPatientImage, processMessagesWithAvatars, processSummaryData} from './helpers';
import {useHandsFreeSpeech} from '../../hooks/useHandsFreeSpeech';
import {useInterviewRecording} from '../../hooks/useInterviewRecording';
import {useUser} from '../../hooks/useUser';
import {SpeechTiming} from '../../types/recording';
import doctorImage from '../../assets/doctor.png';
import patientImageM from '../../assets/patient_m.png';
import {AppContainerOutletContext} from '../common/AppContainer';
import {X} from '../../icons';
import {interviewPath, ROUTES} from '../../utils/routes';
import {useInterviewMedia} from '../../contexts/interviewMedia';

const EMPTY_PATIENT: Patient = {
  name: '',
  id: '',
  avatar: patientImageM,
  online: true,
  basicInfo: {
    age: 0,
    gender: '',
    bloodType: '',
    weight: '',
  },
  symptoms: [],
  allergies: [],
  diet: '',
  illnesses: [],
  medications: [],
  familyHistory: [],
  habits: [],
  workInformation: '',
  medicalHistory: [],
  summary: '',
};

export const ClinicalChat: FC<{mode: 'session' | 'review'}> = ({mode}) => {
  const {t, i18n} = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const {user} = useUser();
  const {setClinicalSimulationActive} = useOutletContext<AppContainerOutletContext>();
  const {interviewId: interviewIdParam} = useParams<{interviewId: string}>();
  const interviewId = interviewIdParam ? Number.parseInt(interviewIdParam, 10) : null;
  const interfaceLanguage: 'en' | 'es' = i18n.resolvedLanguage?.startsWith('es')
    ? 'es'
    : 'en';

  const [feedback, setFeedback] = useState('');
  const [ending, setEnding] = useState(false);
  const [openObservationDialog, setOpenObservationDialog] = useState(false);
  const [isSavingObservation, setIsSavingObservation] = useState(false);
  const [openWelcomeModal, setOpenWelcomeModal] = useState(false);
  const [resumePromptOpen, setResumePromptOpen] = useState(false);
  const [forcingTermination, setForcingTermination] = useState(false);
  const [forceTerminationError, setForceTerminationError] = useState(false);
  const [simulationAccepted, setSimulationAccepted] = useState(false);
  const [contextPanelOpen, setContextPanelOpen] = useState(false);
  const [evaluationData, setEvaluationData] = useState<InterviewEvaluationResponse | null>(null);
  const audioAutoPlayEnabled = true;
  const [isPatientSpeaking, setIsPatientSpeaking] = useState(false);
  const [patientTurnActive, setPatientTurnActive] = useState(false);
  const [hypothesesSubmitted, setHypothesesSubmitted] = useState(false);
  const [submittedHypotheses, setSubmittedHypotheses] = useState<
    {id: number; hypothesisText: string; hypothesisOrder: number}[]
  >([]);
  const [messages, setMessages] = useState<Message[]>();
  const [isLoading, setIsLoading] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [interview, setInterview] = useState<CompleteInterviewResponse>();
  const [patient, setPatient] = useState<Patient>(EMPTY_PATIENT);
  const [headerControlsTarget, setHeaderControlsTarget] = useState<HTMLElement | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isRegenerating, setIsRegenerating] = useState(false);

  const interviewRequestRef = useRef(0);
  const summaryRequestRef = useRef(0);
  const welcomeShownRef = useRef(false);
  const resumePromptShownRef = useRef(false);
  const observationSnapshotRef = useRef('');
  const regenerateActiveRef = useRef(false);
  const recordingRef = useRef<{
    pause: () => void;
    resume: () => void;
    finalize: () => Promise<boolean>;
    resumeAudioGraph: () => Promise<void>;
    recordStudentTurn: (messageId: number, sequence: number, transcript: string, timing?: SpeechTiming) => void;
    beginStudentTurn: () => void;
    endStudentTurn: () => void;
    discardStudentTurn: () => void;
  } | null>(null);
  const media = useInterviewMedia();

  const isOwner = interview?.isOwner ?? false;
  const isCompleted = interview?.status === 'completed';
  // Terminal interviews (completed or interrupted) can no longer be continued;
  // they are shown in review with whatever transcript was preserved.
  const isTerminal = isCompleted || interview?.status === 'interrupted';
  const isInterviewOpen = Boolean(interview) && !isTerminal && mode === 'session';
  const isSimulationActive = isInterviewOpen && simulationAccepted;
  const studentName = user?.name?.trim() || t('clinicalChat.call.student');

  useEffect(() => {
    setClinicalSimulationActive(isInterviewOpen);
    return () => setClinicalSimulationActive(false);
  }, [isInterviewOpen, setClinicalSimulationActive]);

  // While an interview is in progress the student is locked into the session
  // view: the only way out is to finish the interview (which saves it). The app
  // uses a declarative BrowserRouter (not a data router), so useBlocker is not
  // available; instead we pin the history entry to intercept the back button and
  // warn on tab close/reload.
  const shouldLockSession = isSimulationActive && isOwner;
  useEffect(() => {
    if (!shouldLockSession) return undefined;

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    // Push a sentinel entry so the first Back press lands here instead of leaving.
    window.history.pushState(null, '', window.location.href);
    const handlePopState = () => {
      // Re-anchor: cancel the attempted navigation away from the session.
      window.history.pushState(null, '', window.location.href);
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('popstate', handlePopState);
    };
  }, [shouldLockSession]);

  useEffect(() => {
    setHeaderControlsTarget(null);
    if (!isInterviewOpen) return undefined;

    const findHeaderControlsTarget = () => {
      setHeaderControlsTarget(
        document.getElementById('clinical-call-header-controls'),
      );
    };
    findHeaderControlsTarget();

    const observer = new MutationObserver(findHeaderControlsTarget);
    observer.observe(document.body, {childList: true, subtree: true});
    return () => observer.disconnect();
  }, [isInterviewOpen]);

  useEffect(() => {
    if (isSimulationActive && isOwner) {
      void Promise.all([media.startCamera(), media.startMicrophone()]);
    }
  }, [isOwner, isSimulationActive, media.startCamera, media.startMicrophone]);

  const fetchInterview = useCallback(async () => {
    if (!interviewId) return;
    const requestId = ++interviewRequestRef.current;
    const interviewData = await getInterview(interviewId.toString(), interfaceLanguage);
    if (requestId !== interviewRequestRef.current) return;

    setInterview(interviewData);
    setMessages(processMessagesWithAvatars(interviewData.messages, interviewData.patientGender));
    setPatient((current) => ({
      ...current,
      name: interviewData.patientName || t('clinicalChat.call.patient'),
      id: interviewData.clinicalCase?.id.toString() || 'unknown',
      avatar:
        interviewData.patientPhoto || getPatientImage(interviewData.patientGender || undefined),
      basicInfo: {
        age: interviewData.clinicalCase?.age || 0,
        gender: interviewData.patientGender || '',
        bloodType: '',
        weight: interviewData.clinicalCase?.weightInKg
          ? `${interviewData.clinicalCase.weightInKg} kg`
          : t('patientProfile.weightNotSpecified'),
      },
    }));

    if (interviewData.status === 'completed' && interviewData.interviewEvaluation) {
      setEvaluationData({
        interview: {
          id: interviewData.id,
          publicId: interviewData.publicId,
          userId: interviewData.userId,
          clinicalCaseId: interviewData.clinicalCaseId,
          status: interviewData.status,
          startTime: interviewData.startTime,
          endTime: interviewData.endTime,
          totalDuration: interviewData.totalDuration || 0,
          createdAt: interviewData.createdAt,
          clinicalCase: interviewData.clinicalCase,
          progressSummary: interviewData.progressSummary,
          interviewMetadata: interviewData.interviewMetadata,
          messages: interviewData.messages,
          sessionNotes: interviewData.sessionNotes,
          isOwner: interviewData.isOwner,
          hypotheses: interviewData.hypotheses,
        },
        evaluationResults: interviewData.interviewEvaluation.evaluationResults,
      });
    }

    if (interviewData.hypotheses?.length) {
      setSubmittedHypotheses(interviewData.hypotheses);
      setHypothesesSubmitted(true);
    }

    try {
      const sessionNote = await getSessionNote(interviewId.toString());
      if (sessionNote && requestId === interviewRequestRef.current) {
        setFeedback(sessionNote.notesContent);
      }
    } catch (error) {
      console.error('Failed to load session note:', error);
    }

    if (mode === 'session' && !interviewData.startTime) {
      navigate(interviewPath(interviewData.id, 'calibration'), {replace: true});
      return;
    }

    const isTerminalStatus =
      interviewData.status === 'completed' || interviewData.status === 'interrupted';
    const justStarted = Boolean((location.state as {justStarted?: boolean} | null)?.justStarted);
    // A re-entry is a session that already started (has a clock) reached without
    // the fresh-start flag: the tab was closed or the user navigated back in.
    const isReentry =
      mode === 'session' &&
      !isTerminalStatus &&
      interviewData.isOwner &&
      Boolean(interviewData.startTime) &&
      !justStarted;

    if (
      mode === 'session' &&
      !isTerminalStatus &&
      interviewData.messages?.length === 0 &&
      interviewData.isOwner &&
      !interviewData.startTime &&
      !welcomeShownRef.current
    ) {
      welcomeShownRef.current = true;
      setOpenWelcomeModal(true);
    } else if (isReentry && !resumePromptShownRef.current) {
      // Do not auto-resume: ask the student whether to resume or force
      // termination of the unfinished session.
      resumePromptShownRef.current = true;
      setResumePromptOpen(true);
    } else if (interviewData.startTime || interviewData.messages?.length || isTerminalStatus) {
      setSimulationAccepted(true);
    }
  }, [interfaceLanguage, interviewId, location.state, media.cameraState, media.microphoneState, mode, navigate, t]);

  const fetchAndProcessSummary = useCallback(
    async (context: string = 'summary') => {
      if (!interviewId) return;
      const requestId = ++summaryRequestRef.current;
      try {
        const response = await createSummary(interviewId.toString(), interfaceLanguage);
        if (requestId !== summaryRequestRef.current) return;
        if (response.summary_result) {
          setPatient(processSummaryData(response.summary_result));
          setEvaluationData((current) =>
            current
              ? {
                  ...current,
                  interview: {
                    ...current.interview,
                    progressSummary: response.summary_result!,
                  },
                }
              : current,
          );
        }
      } catch (error) {
        console.error(`Failed to fetch ${context}:`, error);
      }
    },
    [interfaceLanguage, interviewId],
  );

  // Regenerate the whole evaluation from the review screen. The backend runs
  // the multimodal analysis first and only then the final text evaluation, so
  // the UI keeps the panel in a loading state until the recording's
  // observation_processing status turns terminal, then re-fetches the interview
  // to pull the freshly stored evaluation.
  const handleRegenerateEvaluation = useCallback(async () => {
    if (!interviewId || regenerateActiveRef.current) return;
    regenerateActiveRef.current = true;
    setIsRegenerating(true);
    const PENDING_STATUSES = ['queued', 'processing'];
    const POLL_INTERVAL_MS = 3000;
    const MAX_POLLS = 200; // ~10 minutes guardrail against an endless poll.
    try {
      await reprocessInterviewRecording(interviewId);
      // Poll the recap until the multimodal pipeline reports a terminal status.
      // The final evaluation is written right after that stage on the backend,
      // so a short settle delay precedes the interview re-fetch.
      for (let polls = 0; polls < MAX_POLLS; polls += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
        if (!regenerateActiveRef.current) return;
        let status: string | undefined;
        try {
          const recap = await getInterviewRecap(interviewId);
          status = recap.observationProcessing?.status;
        } catch (error) {
          console.error('Failed to poll regeneration status:', error);
        }
        if (!status || !PENDING_STATUSES.includes(status)) {
          break;
        }
      }
      // Give the backend a moment to persist the final evaluation that runs
      // immediately after the multimodal stage completes, then refresh.
      await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
      if (!regenerateActiveRef.current) return;
      await fetchInterview();
    } catch (error) {
      console.error('Failed to regenerate evaluation:', error);
    } finally {
      regenerateActiveRef.current = false;
      setIsRegenerating(false);
    }
  }, [fetchInterview, interviewId]);

  useEffect(() => {
    void fetchInterview();
    return () => {
      interviewRequestRef.current += 1;
    };
  }, [fetchInterview]);

  // If the review screen unmounts mid-regeneration, stop the poll loop.
  useEffect(() => () => {
    regenerateActiveRef.current = false;
  }, []);

  useEffect(() => {
    if (!interviewId || !interview || mode !== 'session') return;
    if (isCompleted) {
      return () => {
        summaryRequestRef.current += 1;
      };
    }
    void fetchAndProcessSummary('localized summary');
    const interval = window.setInterval(
      () => void fetchAndProcessSummary('periodic summary'),
      40000,
    );
    return () => {
      summaryRequestRef.current += 1;
      window.clearInterval(interval);
    };
  }, [fetchAndProcessSummary, interview, interviewId, isCompleted, mode]);

  const handleFeedbackBlur = async () => {
    if (!interviewId || !feedback.trim()) return;
    try {
      await updateSessionNote(interviewId.toString(), {notesContent: feedback});
    } catch (error) {
      console.error('Failed to save session note:', error);
    }
  };

  const handleOpenObservationDialog = () => {
    observationSnapshotRef.current = feedback;
    setOpenObservationDialog(true);
  };

  const cancelObservationDialog = () => {
    setFeedback(observationSnapshotRef.current);
    setOpenObservationDialog(false);
  };

  const saveObservation = async () => {
    setIsSavingObservation(true);
    await handleFeedbackBlur();
    observationSnapshotRef.current = feedback;
    setIsSavingObservation(false);
    setOpenObservationDialog(false);
  };

  const handleSendMessage = useCallback(
    async (content: string, timing?: SpeechTiming) => {
      if (!interviewId || isLoading || !content.trim()) return;
      setPatientTurnActive(true);
      await recordingRef.current?.resumeAudioGraph();
      const optimisticMessage: Message = {
        id: Date.now(),
        content,
        createdAt: new Date().toISOString(),
        senderType: 'user',
        interviewId,
        senderAvatar: doctorImage,
      };
      setMessages((current) => [...(current || []), optimisticMessage]);
      setMessageError(null);
      setIsLoading(true);
      try {
        const response = await sendMessage(interviewId.toString(), content);
        const processedMessages = processMessagesWithAvatars(
          response.messages,
          interview?.patientGender,
        ).map((message) =>
          response.newMessageIds.includes(message.id)
            ? {
                ...message,
                messageMetadata: {...message.messageMetadata, isNew: true},
              }
            : message,
        );
        setMessages(processedMessages);
        const studentMessage = processedMessages.find(
          (message) => response.newMessageIds.includes(message.id) && message.senderType === 'user',
        );
        if (studentMessage) {
          recordingRef.current?.recordStudentTurn(
            studentMessage.id,
            Math.max(processedMessages.findIndex((message) => message.id === studentMessage.id), 0),
            studentMessage.content,
            timing,
          );
        }
      } catch (error) {
        console.error('Failed to send message:', error);
        setMessageError(t('clinicalChat.messageSendError'));
        setPatientTurnActive(false);
      } finally {
        setIsLoading(false);
      }
    },
    [interview?.patientGender, interviewId, isLoading, t],
  );

  const speechLanguage =
    interview?.interviewMetadata?.patientResponseLanguage === 'es' ? 'es-ES' : 'en-US';
  const patientHasFloor = patientTurnActive || isLoading || isPatientSpeaking;
  const handleUtteranceCommitted = useCallback(() => {
    setPatientTurnActive(true);
    recordingRef.current?.endStudentTurn();
  }, []);
  const handleUtteranceFailed = useCallback(() => {
    setPatientTurnActive(false);
    recordingRef.current?.discardStudentTurn();
  }, []);
  const handleSpeechStart = useCallback(() => {
    recordingRef.current?.beginStudentTurn();
  }, []);
  const speech = useHandsFreeSpeech({
    language: speechLanguage,
    paused: patientHasFloor,
    disabled: mode !== 'session' || !isOwner || isCompleted || ending,
    autoStart: Boolean(isSimulationActive && isOwner),
    microphoneStream: media.microphoneStream,
    onUtteranceCommitted: handleUtteranceCommitted,
    onSpeechStart: handleSpeechStart,
    onUtteranceFailed: handleUtteranceFailed,
    onUtterance: handleSendMessage,
  });

  useEffect(() => {
    if (!isSimulationActive) speech.stop();
  }, [isSimulationActive, speech.stop]);

  const recording = useInterviewRecording({
    interviewId: interviewId ?? undefined,
    enabled: Boolean(isSimulationActive && isOwner),
    cameraStream: media.cameraStream,
    microphoneStream: media.microphoneStream,
    microphoneState: media.microphoneState,
    cameraEnabled: media.cameraState === 'ready',
    microphoneEnabled: speech.isEnabled && !patientHasFloor,
    patientAudioEnabled: audioAutoPlayEnabled,
    patientAvatar: patient.avatar,
    patientName: patient.name,
  });
  recordingRef.current = recording;

  useEffect(() => {
    if (!isSimulationActive) {
      setElapsedSeconds(0);
      return undefined;
    }
    const updateElapsedTime = () => {
      const interviewStartedAt = interview?.startTime
        ? new Date(interview.startTime).getTime()
        : Number.NaN;
      const elapsed = Number.isFinite(interviewStartedAt)
        ? Math.floor((Date.now() - interviewStartedAt) / 1000)
        : Math.floor(recording.elapsedAt() / 1000);
      setElapsedSeconds(Math.max(0, elapsed));
    };
    updateElapsedTime();
    const timer = window.setInterval(updateElapsedTime, 1000);
    return () => window.clearInterval(timer);
  }, [interview?.startTime, isSimulationActive, recording.elapsedAt]);
  const isEndInterviewDisabled =
    !isOwner
    || isCompleted
    || ending
    || recording.status === 'finalizing';

  const handleEndInterview = () => {
    if (!isOwner) return;
    recording.pause();
    setEnding(true);
    void fetchAndProcessSummary('final summary');
  };
  // Resume the unfinished session: close the prompt and let the simulation
  // reactivate (media and clock resume as usual).
  const handleResumeSession = () => {
    setResumePromptOpen(false);
    setSimulationAccepted(true);
  };
  // Force termination: mark the interview as interrupted (no evaluation) and go
  // to the read-only review with whatever transcript was preserved.
  const handleForceTermination = async () => {
    if (!interviewId || forcingTermination) return;
    setForcingTermination(true);
    setForceTerminationError(false);
    try {
      await interruptInterview(String(interviewId));
      // An interrupted interview has no review; return to the history.
      navigate(ROUTES.interviews, {replace: true});
    } catch (error) {
      console.error('Failed to force interview termination:', error);
      setForceTerminationError(true);
      setForcingTermination(false);
    }
  };
  const cancelHypotheses = () => {
    recording.resume();
    setEnding(false);
  };
  const handleHypothesesSubmitted = async (
    nextEvaluationData: InterviewEvaluationResponse,
  ) => {
    setEvaluationData(nextEvaluationData);
    setEnding(false);
    setHypothesesSubmitted(true);
    await fetchInterview();
    // On finish the interview is not yet completed (multimodal processing keeps
    // running in the background), so return to the history rather than the
    // review. The review becomes reachable once the status turns 'completed'.
    navigate(ROUTES.interviews, {replace: true});
  };

  if (!interviewId || !interview) return null;

  // A terminal interview (completed or interrupted) can no longer run in a
  // session: send the user back to the history instead of the review.
  if (mode === 'session' && isTerminal) {
    return <Navigate to={ROUTES.interviews} replace />;
  }
  // Review is only reachable once the interview is completed (text evaluation
  // ready). Any other status (in_progress, processing, interrupted) is blocked
  // and redirected to the history.
  if (mode === 'review' && !isCompleted) {
    return <Navigate to={ROUTES.interviews} replace />;
  }

  const InterviewLayout = isInterviewOpen
    ? ActiveSimulationLayout
    : SimulationResultsLayout;

  return (
    <InterviewLayout>
      {isInterviewOpen && headerControlsTarget && createPortal(
        <CallToolbar
          elapsedSeconds={elapsedSeconds}
          controlsDisabled={!simulationAccepted}
          endDisabled={isEndInterviewDisabled}
          completed={false}
          onReportObservation={handleOpenObservationDialog}
          onEndInterview={handleEndInterview}
          onOpenContext={() => setContextPanelOpen(true)}
        />,
        headerControlsTarget,
      )}
      {!isSimulationActive && evaluationData && (
        <EvaluationResultsPanel
          evaluationData={evaluationData}
          className="xl:col-start-3 xl:row-start-1"
          canRegenerate={mode === 'review' && isOwner && isCompleted}
          isRegenerating={isRegenerating}
          onRegenerate={handleRegenerateEvaluation}
        />
      )}
      {isInterviewOpen && (
        <CallStage
          className="xl:col-start-2 xl:row-start-1"
          patientAvatar={patient.avatar}
          patientName={patient.name}
          studentName={studentName}
          patientSpeaking={isPatientSpeaking}
          cameraStream={media.cameraStream}
          cameraEnabled={media.cameraState === 'ready'}
          cameraStarting={media.cameraState === 'loading'}
          cameraErrorCode={['permission-denied', 'unavailable', 'unsupported'].includes(media.cameraState) ? media.cameraState : null}
          onRetryCamera={() => void media.startCamera()}
        />
      )}

      <section className={`flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl bg-white shadow-transcript xl:row-start-1 ${
        isInterviewOpen ? 'xl:col-start-3' : 'xl:col-start-2'
      }`}>
        {isTerminal ? (
          <InterviewRecap
            interviewId={interviewId}
            messages={messages}
            infoDisabled={isRegenerating}
          />
        ) : (
          <>
            <ConversationTranscript
              interviewId={interviewId}
              messages={messages}
              isListening={speech.isListening && !patientHasFloor}
              audioLevel={speech.audioLevel}
              patientAudioLevel={recording.patientAudioLevel}
              hasPendingUtterance={speech.hasPendingUtterance}
              isSubmittingUtterance={speech.isSubmittingUtterance}
              onSubmitUtterance={speech.submitUtterance}
              isLoading={isLoading}
              audioAutoPlayEnabled={audioAutoPlayEnabled}
              playbackReady={recording.status !== 'idle'}
              onPatientSpeakingChange={setIsPatientSpeaking}
              captureEnabled={recording.isCapturing}
              routePatientAudio={recording.routePatientAudio}
              onPatientTurnStart={recording.beginPatientTurn}
              onPatientTurnEnd={recording.endPatientTurn}
              onPatientTurnComplete={() => {
                setPatientTurnActive(false);
              }}
            />
            {(speech.errorCode || messageError) && (
              <div className="mx-3 mb-2 rounded-lg bg-amber-50 px-3 py-2 text-left text-xs text-amber-800" role="alert">
                {messageError || t(`clinicalChat.call.speechErrors.${speech.errorCode}`)}
              </div>
            )}
            {recording.errorCode && (
              <div className="mx-3 mb-2 rounded-lg bg-amber-50 px-3 py-2 text-left text-xs text-amber-800" role="alert">
                {t(`clinicalChat.recording.errors.${recording.errorCode}`)}
              </div>
            )}
            {!isOwner && (
              <div className="border-t border-slate-200 p-3 text-center text-sm text-slate-500">
                {t('clinicalChat.readOnlyMode')}
              </div>
            )}
          </>
        )}
      </section>

      {contextPanelOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 cursor-default border-0 bg-black/35 p-0 xl:hidden"
          onClick={() => setContextPanelOpen(false)}
          aria-label={t('clinicalChat.call.closeInformation')}
        />
      )}
      <aside
        className={`fixed inset-y-0 right-0 z-50 flex w-context-panel min-h-0 min-w-0 flex-col gap-2 overflow-y-auto bg-slate-100 p-2 shadow-xl transition-transform duration-200 scrollbar-hidden xl:static xl:z-auto xl:col-start-1 xl:row-start-1 xl:w-full xl:translate-x-0 xl:bg-transparent xl:p-0 xl:shadow-none ${
          contextPanelOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
        aria-label={t('clinicalChat.call.contextPanel')}
      >
        <div className="flex justify-end xl:hidden">
          <button
            type="button"
            onClick={() => setContextPanelOpen(false)}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-slate-600 shadow-sm [&_svg]:h-4 [&_svg]:w-4"
            aria-label={t('clinicalChat.call.closeInformation')}
          >
            <X color="currentColor" />
          </button>
        </div>
        <PatientProfile
          patient={patient}
          caseTitle={interview.clinicalCase?.title}
          personality={interview.personality}
        />
        {hypothesesSubmitted && submittedHypotheses.length > 0 && (
          <section className="overflow-hidden rounded-xl bg-white shadow-panel-subtle">
            <h3 className="component-title flex min-h-12 items-center border-b border-slate-200 px-4 text-left">
              {t('clinicalChat.submittedHypotheses')}
            </h3>
            <div className="space-y-2 p-4">
              {[...submittedHypotheses]
                .sort((left, right) => left.hypothesisOrder - right.hypothesisOrder)
                .map((hypothesis) => (
                  <div key={hypothesis.id} className="flex items-start gap-2 rounded-lg bg-slate-50 p-2 text-left text-xs leading-4 text-slate-700">
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-blue-700">
                      {hypothesis.hypothesisOrder}
                    </span>
                    <span>{hypothesis.hypothesisText}</span>
                  </div>
                ))}
            </div>
          </section>
        )}
        {isCompleted && <TeacherFeedbackSection interviewId={interview.id} />}
      </aside>

      <Modal
        size="large"
        open={ending && !hypothesesSubmitted}
        closeAction={cancelHypotheses}
        closeOnOutsideClick={false}
        hasActions
        ariaLabel={t('clinicalChat.clinicalHypotheses')}
      >
        <ClinicalHypotheses
          onCancel={cancelHypotheses}
          beforeComplete={async () => {
            await recording.finalize();
          }}
          onHypothesesSubmitted={handleHypothesesSubmitted}
        />
      </Modal>
      <Modal
        size="medium"
        open={openObservationDialog}
        closeAction={cancelObservationDialog}
        hasActions
        ariaLabel={t('clinicalChat.reportObservation')}
      >
        <div className="dialog-shell">
          <header className="dialog-header">
            <h2 className="dialog-title">
              {t('clinicalChat.reportObservation')}
            </h2>
          </header>
          <div className="dialog-content">
            <p className="mb-3 text-sm leading-6 text-slate-600">
              {t('clinicalChat.observationDescription')}
            </p>
            <textarea
              value={feedback}
              onChange={(event) => setFeedback(event.target.value)}
              placeholder={isOwner ? t('clinicalChat.observationPlaceholder') : t('clinicalChat.readOnlyFeedback')}
              disabled={!isOwner || isSavingObservation}
              rows={7}
              className="w-full resize-none rounded-control border border-border bg-surface px-3 py-2.5 text-sm leading-6 text-slate-700 placeholder:text-slate-400 hover:border-neutral-400 disabled:cursor-not-allowed disabled:bg-neutral-100"
            />
          </div>
          <footer className="dialog-footer">
            <div className="dialog-actions">
              <button
                type="button"
                onClick={cancelObservationDialog}
                disabled={isSavingObservation}
                className="dialog-action dialog-action--secondary"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                onClick={() => void saveObservation()}
                disabled={!isOwner || !feedback.trim() || isSavingObservation}
                className="dialog-action dialog-action--primary"
              >
                {isSavingObservation ? t('common.loading') : t('common.save')}
              </button>
            </div>
          </footer>
        </div>
      </Modal>
      <WelcomeModal
        isOpen={openWelcomeModal}
        onAccept={() => {
          if (!interviewId) return;
          void startInterview(interviewId)
            .then((startedInterview) => {
              setInterview((current) => current ? {...current, startTime: startedInterview.startTime} : current);
              void recording.resumeAudioGraph();
              setSimulationAccepted(true);
              setOpenWelcomeModal(false);
            })
            .catch(() => setMessageError(t('calibration.startError')));
        }}
        onCancel={() => navigate(interviewPath(interviewId, 'calibration'), {replace: true})}
      />
      <Modal
        size="medium"
        open={resumePromptOpen}
        closeAction={() => undefined}
        closeOnOutsideClick={false}
        hasActions
        ariaLabel={t('clinicalChat.resumeSession.title')}
      >
        <div className="dialog-shell">
          <header className="dialog-header">
            <h2 className="dialog-title">{t('clinicalChat.resumeSession.title')}</h2>
          </header>
          <div className="dialog-content">
            <p className="text-sm leading-6 text-slate-600">
              {t('clinicalChat.resumeSession.description')}
            </p>
            {forceTerminationError && (
              <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
                {t('clinicalChat.resumeSession.forceError')}
              </p>
            )}
          </div>
          <footer className="dialog-footer">
            <div className="dialog-actions">
              <button
                type="button"
                onClick={() => void handleForceTermination()}
                disabled={forcingTermination}
                className="dialog-action dialog-action--secondary"
              >
                {forcingTermination
                  ? t('common.loading')
                  : t('clinicalChat.resumeSession.forceTermination')}
              </button>
              <button
                type="button"
                onClick={handleResumeSession}
                disabled={forcingTermination}
                className="dialog-action dialog-action--primary"
              >
                {t('clinicalChat.resumeSession.resume')}
              </button>
            </div>
          </footer>
        </div>
      </Modal>
    </InterviewLayout>
  );
};

