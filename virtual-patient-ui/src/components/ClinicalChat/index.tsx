import {FC, useCallback, useEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {useTranslation} from 'react-i18next';
import {Navigate, useNavigate, useOutletContext, useParams} from 'react-router-dom';
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
import {completeInterview, createSummary, sendMessage} from '../../services/interviews';
import {getInterview} from '../../services/interviews/getInterview';
import {getSessionNote, updateSessionNote} from '../../services/sessionNote';
import {CompleteInterviewResponse} from '../../types/interview';
import {Patient} from '../../types/patient';
import {Message} from '../../types/message';
import {InterviewEvaluationResponse} from '../../types/evaluation';
import {EvaluationResultsPanel} from '../Evaluation';
import {getPatientImage, processMessagesWithAvatars, processSummaryData} from './helpers';
import {useHandsFreeSpeech} from '../../hooks/useHandsFreeSpeech';
import {useLocalCamera} from '../../hooks/useLocalCamera';
import {useInterviewRecording} from '../../hooks/useInterviewRecording';
import {useUser} from '../../hooks/useUser';
import {SpeechTiming} from '../../types/recording';
import doctorImage from '../../assets/doctor.png';
import patientImageM from '../../assets/patient_m.png';
import {AppContainerOutletContext} from '../common/AppContainer';
import {X} from '../../icons';
import {interviewPath} from '../../utils/routes';

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

const INTERVIEW_DURATION_LIMIT_SECONDS = 60 * 60;

export const ClinicalChat: FC<{mode: 'session' | 'review'}> = ({mode}) => {
  const {t, i18n} = useTranslation();
  const navigate = useNavigate();
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
  const [durationLimitExceeded, setDurationLimitExceeded] = useState(false);
  const [durationLimitCompletionError, setDurationLimitCompletionError] = useState(false);

  const interviewRequestRef = useRef(0);
  const summaryRequestRef = useRef(0);
  const welcomeShownRef = useRef(false);
  const durationLimitHandledRef = useRef(false);
  const observationSnapshotRef = useRef('');
  const recordingRef = useRef<{
    pause: () => void;
    resume: () => void;
    finalize: () => Promise<boolean>;
    resumeAudioGraph: () => Promise<void>;
    recordStudentTurn: (messageId: number, sequence: number, transcript: string, timing?: SpeechTiming) => void;
  } | null>(null);
  const camera = useLocalCamera(false);

  const isOwner = interview?.isOwner ?? false;
  const isCompleted = interview?.status === 'completed';
  const isInterviewOpen = Boolean(interview) && !isCompleted && mode === 'session';
  const isSimulationActive = isInterviewOpen && simulationAccepted;
  const studentName = [user?.firstName, user?.lastName].filter(Boolean).join(' ').trim() || t('clinicalChat.call.student');

  useEffect(() => {
    setClinicalSimulationActive(isInterviewOpen);
    return () => setClinicalSimulationActive(false);
  }, [isInterviewOpen, setClinicalSimulationActive]);

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
    if (isSimulationActive && isOwner) void camera.start();
    else camera.stop();
  }, [camera.start, camera.stop, isOwner, isSimulationActive]);

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

    if (
      mode === 'session' &&
      interviewData.status !== 'completed' &&
      interviewData.messages?.length === 0 &&
      interviewData.isOwner &&
      !welcomeShownRef.current
    ) {
      welcomeShownRef.current = true;
      setOpenWelcomeModal(true);
    } else if (interviewData.messages?.length || interviewData.status === 'completed') {
      setSimulationAccepted(true);
    }
  }, [interfaceLanguage, interviewId, mode, t]);

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

  useEffect(() => {
    void fetchInterview();
    return () => {
      interviewRequestRef.current += 1;
    };
  }, [fetchInterview]);

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
  }, []);
  const handleUtteranceFailed = useCallback(() => {
    setPatientTurnActive(false);
  }, []);
  const speech = useHandsFreeSpeech({
    language: speechLanguage,
    paused: patientHasFloor,
    disabled: mode !== 'session' || !isOwner || isCompleted || ending,
    autoStart: Boolean(isSimulationActive && isOwner),
    onUtteranceCommitted: handleUtteranceCommitted,
    onUtteranceFailed: handleUtteranceFailed,
    onUtterance: handleSendMessage,
  });

  useEffect(() => {
    if (!isSimulationActive) speech.stop();
  }, [isSimulationActive, speech.stop]);

  const recording = useInterviewRecording({
    interviewId: interviewId ?? undefined,
    enabled: Boolean(isSimulationActive && isOwner),
    cameraStream: camera.stream,
    cameraEnabled: camera.isEnabled,
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
  };

  useEffect(() => {
    if (
      elapsedSeconds < INTERVIEW_DURATION_LIMIT_SECONDS
      || !isSimulationActive
      || !isOwner
      || durationLimitHandledRef.current
    ) return;

    durationLimitHandledRef.current = true;
    setDurationLimitExceeded(true);
    setDurationLimitCompletionError(false);
    setOpenObservationDialog(false);
    setEnding(true);
    recording.pause();
    camera.stop();
    setIsPatientSpeaking(false);

    void (async () => {
      try {
        await fetchAndProcessSummary('duration limit summary');
        await recording.finalize();
        const nextEvaluationData = await completeInterview(
          String(interviewId),
          'duration_limit_exceeded',
        );
        await handleHypothesesSubmitted(nextEvaluationData);
      } catch (error) {
        console.error('Failed to complete interview after duration limit:', error);
        setDurationLimitCompletionError(true);
      }
    })();
  }, [
    camera.stop,
    elapsedSeconds,
    fetchAndProcessSummary,
    interviewId,
    isOwner,
    isSimulationActive,
    recording,
  ]);
  if (!interviewId || !interview) return null;

  if (mode === 'session' && isCompleted) {
    return <Navigate to={interviewPath(interviewId, 'review')} replace />;
  }
  if (mode === 'review' && !isCompleted) {
    return <Navigate to={interviewPath(interviewId, 'session')} replace />;
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
        />
      )}
      {isInterviewOpen && (
        <CallStage
          className="xl:col-start-2 xl:row-start-1"
          patientAvatar={patient.avatar}
          patientName={patient.name}
          studentName={studentName}
          patientSpeaking={isPatientSpeaking}
          cameraStream={camera.stream}
          cameraEnabled={camera.isEnabled}
          cameraStarting={camera.isStarting}
          cameraErrorCode={camera.errorCode}
          onRetryCamera={() => void camera.start()}
        />
      )}

      <section className={`flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl bg-white shadow-transcript xl:row-start-1 ${
        isInterviewOpen ? 'xl:col-start-3' : 'xl:col-start-2'
      }`}>
        {isCompleted ? (
          <InterviewRecap interviewId={interviewId} messages={messages} />
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
            {recording.status === 'finalizing' && (
              <div className="mx-3 mb-2 rounded-lg bg-blue-50 px-3 py-2 text-left text-xs text-blue-800" role="status">
                {t('clinicalChat.recording.uploading', {progress: Math.round(recording.uploadProgress * 100)})}
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
        closeAction={durationLimitExceeded ? () => undefined : cancelHypotheses}
        closeOnOutsideClick={false}
        hasActions={!durationLimitExceeded}
        ariaLabel={t('clinicalChat.clinicalHypotheses')}
      >
        {durationLimitExceeded ? (
          <div className="flex h-full flex-col justify-center p-6 text-left sm:p-8">
            <h2 className="text-xl font-semibold text-slate-900">
              {t('clinicalChat.durationLimit.title')}
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              {t('clinicalChat.durationLimit.hypothesesUnavailable')}
            </p>
            <p className={`mt-4 rounded-lg px-4 py-3 text-sm ${
              durationLimitCompletionError
                ? 'bg-red-50 text-red-700'
                : 'bg-blue-50 text-blue-700'
            }`} role={durationLimitCompletionError ? 'alert' : 'status'}>
              {durationLimitCompletionError
                ? t('clinicalChat.durationLimit.completionFailed')
                : t('clinicalChat.durationLimit.finalizing')}
            </p>
          </div>
        ) : (
          <ClinicalHypotheses
            onCancel={cancelHypotheses}
            beforeComplete={async () => {
              await recording.finalize();
            }}
            onHypothesesSubmitted={handleHypothesesSubmitted}
          />
        )}
      </Modal>
      <Modal
        size="medium"
        open={openObservationDialog}
        closeAction={cancelObservationDialog}
        hasActions
        ariaLabel={t('clinicalChat.reportObservation')}
      >
        <div className="flex flex-col overflow-hidden rounded-panel bg-surface text-left">
          <header className="border-b border-border px-5 py-3.5">
            <h2 className="text-lg font-semibold text-slate-800">
              {t('clinicalChat.reportObservation')}
            </h2>
          </header>
          <div className="px-5 py-4">
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
          <footer className="flex justify-end px-5 py-3.5">
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
          void recording.resumeAudioGraph();
          setSimulationAccepted(true);
          setOpenWelcomeModal(false);
        }}
        onCancel={() => navigate(-1)}
      />
    </InterviewLayout>
  );
};
