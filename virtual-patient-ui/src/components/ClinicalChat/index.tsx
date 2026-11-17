import {useReviewRefresh} from './useReviewRefresh';
import {InterviewContentLoading} from './InterviewContentLoading';
import {ResumeSessionDialog} from './ResumeSessionDialog';
import {FC, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Navigate, useLocation, useNavigate, useParams} from 'react-router-dom';
import {PatientProfile} from './PatientProfile';
import {CalibrationReferenceDialog} from './CalibrationReferenceDialog';
import {Modal} from '../common';
import {ClinicalHypotheses} from './ClinicalHypotheses';
import {WelcomeModal} from './WelcomeModal';
import {HumanRatingPanel} from '../Evaluation/HumanRatingPanel';
import {AssessmentSelector} from '../Evaluation/AssessmentSelector';
import {CallStage} from './CallStage';
import {CallTimer, CallToolbar} from './CallToolbar';
import {ConversationTranscript} from './ConversationTranscript';
import {preparePatientAudio} from '../../services/speech/preparePatientAudio';
import {InterviewRecap} from './InterviewRecap';
import {ActiveSimulationLayout, SimulationResultsLayout} from './InterviewLayouts';
import {
  completeInterview,
  interruptInterview,
  sendMessage,
  startInterview,
} from '../../services/interviews';
import {getInterview} from '../../services/interviews/getInterview';
import {CompleteInterviewResponse} from '../../types/interview';
import {Patient} from '../../types/patient';
import {Message} from '../../types/message';
import {InterviewEvaluationResponse} from '../../types/evaluation';
import {getPatientImage, processMessagesWithAvatars, processSummaryData} from './helpers';
import {useHandsFreeSpeech} from '../../hooks/useHandsFreeSpeech';
import {useInterviewRecording} from '../../hooks/useInterviewRecording';
import {resumeTurnInterview} from '../../services/recordings/turns';
import {useUser} from '../../hooks/useUser';
import {SpeechTiming, InterviewRecap as InterviewRecapData, StudentCaptureTiming} from '../../types/recording';
import doctorImage from '../../assets/doctor.png';
import patientImageM from '../../assets/patient_m.png';
import {InterviewResumeState, interviewPath, ROUTES} from '../../utils/routes';
import {useInterviewMedia} from '../../contexts/interviewMedia';

const measureResponse = (stage: string, start: number | undefined, requestId?: string) => {
  if (!import.meta.env.DEV || start === undefined || typeof performance.measure !== 'function') return;
  performance.measure('patient-response:' + stage, {
    start,
    end: performance.now(),
    detail: {requestId},
  });
};

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
  const {user} = useUser();
  const {interviewId} = useParams<{interviewId: string}>();
  return <ClinicalChatContent key={`${user?.id}:${user?.role}:${interviewId}:${mode}`} mode={mode} />;
};

const ClinicalChatContent: FC<{mode: 'session' | 'review'}> = ({mode}) => {
  const {t, i18n} = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const {user} = useUser();
  const {interviewId: interviewIdParam} = useParams<{interviewId: string}>();
  const interviewId = interviewIdParam ? Number.parseInt(interviewIdParam, 10) : null;
  const interfaceLanguage: 'en' | 'es' = i18n.resolvedLanguage?.startsWith('es') ? 'es' : 'en';

  const [ending, setEnding] = useState(false);
  const [sealingCapture, setSealingCapture] = useState(false);
  const [captureSealed, setCaptureSealed] = useState(false);
  const [interviewLoadError, setInterviewLoadError] = useState(false);
  const [interviewLoading, setInterviewLoading] = useState(true);
  const [retryingCompletion, setRetryingCompletion] = useState(false);
  const [completionRetryError, setCompletionRetryError] = useState(false);
  const [openWelcomeModal, setOpenWelcomeModal] = useState(false);
  const [acceptingWelcome, setAcceptingWelcome] = useState(false);
  const [welcomeError, setWelcomeError] = useState(false);
  const acceptingWelcomeRef = useRef(false);
  const [resumePromptOpen, setResumePromptOpen] = useState(false);
  const [forcingTermination, setForcingTermination] = useState(false);
  const [resumingInterview, setResumingInterview] = useState(false);
  const resumeRequestRef = useRef<string | null>(null);
  const [forceTerminationError, setForceTerminationError] = useState(false);
  const [simulationAccepted, setSimulationAccepted] = useState(false);
  const preparedAudioRef = useRef<HTMLAudioElement | null>(null);
  const audioAutoPlayEnabled = true;
  const [isPatientSpeaking, setIsPatientSpeaking] = useState(false);
  const [patientTurnActive, setPatientTurnActive] = useState(false);
  const [hypothesesSubmitted, setHypothesesSubmitted] = useState(false);
  const [messages, setMessages] = useState<Message[]>();
  const [isLoading, setIsLoading] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [interview, setInterview] = useState<CompleteInterviewResponse>();
  const [patient, setPatient] = useState<Patient>(EMPTY_PATIENT);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  // Bubble times come from the capture clock shown in the header, never from server timestamps.
  const [messageTimes, setMessageTimes] = useState<Record<number, number>>({});
  const speechStartClockRef = useRef<number | null>(null);
  const [recapData, setRecapData] = useState<InterviewRecapData | null>(null);
  const [seekRequest, setSeekRequest] = useState<{
    turnId: string;
    requestId: number;
  } | null>(null);

  const interviewRequestRef = useRef(0);
  const interviewReadRef = useRef<Promise<CompleteInterviewResponse | undefined> | null>(null);
  const interviewAbortRef = useRef<AbortController | null>(null);
  const welcomeShownRef = useRef(false);
  const resumePromptShownRef = useRef(false);
  const freshSessionRef = useRef({
    interviewId,
    accepted: Boolean((location.state as {justStarted?: boolean} | null)?.justStarted),
    resume: (location.state as {resume?: InterviewResumeState} | null)?.resume,
  });
  const sendInFlightRef = useRef(false);
  const utteranceInFlightRef = useRef(false);
  const pendingMessageRef = useRef<{content: string; timing?: SpeechTiming; requestId: string; captureTiming?: StudentCaptureTiming; clockMs?: number} | null>(null);
  const deferredUtteranceRef = useRef<{content: string; timing?: SpeechTiming} | null>(null);
  const [lostDeferredUtterance, setLostDeferredUtterance] = useState<string | null>(null);
  const audioSubmittedAtRef = useRef<number | undefined>(undefined);
  const responsePlaybackRef = useRef<{
    messageId: number;
    requestId: string;
    submittedAt?: number;
    receivedAt: number;
    startedAt?: number;
  } | null>(null);
  const endingRef = useRef(false);
  const patientFloorRef = useRef(false);
  const forcingTerminationRef = useRef(false);
  const recordingRef = useRef<{
    prepareStudentTurn?: (timing?: SpeechTiming) => Promise<StudentCaptureTiming>;
    submitStudentTurn: (requestId: string) => void;
    returnFloorToStudent: () => void;
    markSpeechStart: () => void;
    elapsedAt: () => number;
    syncPending?: boolean;
    pause: () => void;
    resume: () => void;
    finalize: (preserveOnly?: boolean, onProgress?: (fraction: number) => void) => Promise<boolean>;
    resumeAudioGraph: () => Promise<void>;
    recordStudentTurn: (messageId: number) => void;
    segmentId: string | null;
  } | null>(null);
  const utteranceRequestId = useRef<string | null>(null);
  // The greeting (or a reply pending on resume) plays first; capture opens its clip when arming.
  const initialPatientMessageIdRef = useRef<number | null>(null);
  const media = useInterviewMedia();

  useEffect(() => {
    if (mode === 'session' && (location.state as {justStarted?: boolean} | null)?.justStarted) {
      navigate(location.pathname, {replace: true, state: {...location.state, justStarted: false}});
    }
  }, [location.pathname, location.state, mode, navigate]);

  const isOwner = interview?.isOwner ?? false;
  const isCompleted = interview?.status === 'completed';
  // Terminal interviews (completed or interrupted) can no longer be continued;
  // they are shown in review with whatever transcript was preserved.
  const isTerminal = isCompleted || interview?.status === 'interrupted';
  const captureFinalized = interview?.lifecycle?.phase === 'capture_finalized';
  const isInterviewOpen = interview?.status === 'in_progress' && !captureFinalized && mode === 'session';
  const canRetryCompletion = Boolean(interview?.lifecycle?.canComplete || interview?.lifecycle?.canRetryCompletion) || (interview?.status === 'interrupted' && interview.interviewMetadata?.completionProcessing?.status === 'failed');
  const isSimulationActive = isInterviewOpen && simulationAccepted;
  const studentName = user?.name?.trim() || t('clinicalChat.call.student');
  const evaluationData = useMemo<InterviewEvaluationResponse | null>(() => {
    if (!interview || !isCompleted || (!interview.interviewEvaluation && !interview.multimodalInterviewEvaluation)) return null;
    return {interview, evaluationResults: interview.interviewEvaluation?.evaluationResults ?? [],
      multimodalEvaluationResults: interview.multimodalInterviewEvaluation?.evaluationResults ?? []};
  }, [interview, isCompleted]);

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
    if (isSimulationActive && isOwner) {
      void Promise.all([media.startCamera(), media.startMicrophone()]);
    }
  }, [isOwner, isSimulationActive, media.startCamera, media.startMicrophone]);

  const fetchInterview = useCallback(() => {
    if (interviewReadRef.current) return interviewReadRef.current;
    const read = async () => {
      if (!interviewId) return;
      const requestId = ++interviewRequestRef.current;
      const controller = new AbortController();
      interviewAbortRef.current = controller;
      setInterviewLoading(true);
      setInterviewLoadError(false);
      try {
        const interviewData = await getInterview(interviewId.toString(), interfaceLanguage, controller.signal);
        if (requestId !== interviewRequestRef.current) return;

        setInterview(interviewData);
        if (mode === 'session' && (interviewData.status === 'processing' || interviewData.lifecycle?.canComplete || interviewData.lifecycle?.canRetryCompletion)) {
          navigate(interviewPath(interviewId, 'review'), {replace: true});
          return interviewData;
        }
        const resume = freshSessionRef.current.accepted ? freshSessionRef.current.resume : undefined;
        const openingMessageId = mode === 'session' && interviewData.status === 'in_progress'
          ? resume ? resume.pendingPatientMessageId
            : interviewData.messages?.length === 1 && interviewData.messages[0].senderType !== 'user'
              ? interviewData.messages[0].id : null
          : null;
        setMessages(processMessagesWithAvatars(interviewData.messages, interviewData.patientGender)?.map((message) =>
          message.id === openingMessageId ? {...message, messageMetadata: {...message.messageMetadata, isNew: true}} : message));
        if (openingMessageId != null) setPatientTurnActive(true);
        initialPatientMessageIdRef.current = openingMessageId ?? null;
        setPatient((current) => {
          const profile: Patient = {
            ...(mode === 'review' ? EMPTY_PATIENT : current),
            name: interviewData.patientName || t('clinicalChat.call.patient'),
            id: interviewData.clinicalCase?.id.toString() || 'unknown',
            avatar: interviewData.patientPhoto || getPatientImage(interviewData.patientGender || undefined),
            basicInfo: {
              age: interviewData.clinicalCase?.age || 0,
              gender: interviewData.patientGender || '',
              bloodType: '',
              weight: interviewData.clinicalCase?.weightInKg
                ? `${interviewData.clinicalCase.weightInKg} kg`
                : t('patientProfile.weightNotSpecified'),
            },
          };
          return interviewData.progressSummary ? processSummaryData(interviewData.progressSummary)(profile) : profile;
        });

        if (interviewData.hypotheses?.length) {
          setHypothesesSubmitted(true);
        }

        if (mode === 'session' && !interviewData.startTime && !freshSessionRef.current.accepted) {
          navigate(ROUTES.calibration, {replace: true, state: {draftInterviewId: Number(interviewData.id)}});
          return;
        }

        const isTerminalStatus =
          interviewData.status === 'completed' || interviewData.status === 'interrupted';
        const justStarted = freshSessionRef.current.interviewId === interviewId && freshSessionRef.current.accepted;
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
          interviewData.isOwner &&
          justStarted &&
          !welcomeShownRef.current
        ) {
          welcomeShownRef.current = true;
          setOpenWelcomeModal(true);
        } else if (isReentry) {
          setSimulationAccepted(false);
          if (!resumePromptShownRef.current) {
            resumePromptShownRef.current = true;
            setResumePromptOpen(true);
          }
        } else if (!welcomeShownRef.current && (interviewData.startTime || interviewData.messages?.length || isTerminalStatus)) {
          setSimulationAccepted(true);
        }
        return interviewData;
      } catch (error) {
        if (controller.signal.aborted || requestId !== interviewRequestRef.current) return;
        console.error('Failed to load interview:', error);
        setInterviewLoadError(true);
      } finally {
        if (requestId === interviewRequestRef.current) setInterviewLoading(false);
      }
    };
    const pending = read();
    interviewReadRef.current = pending;
    void pending.finally(() => {
      if (interviewReadRef.current === pending) interviewReadRef.current = null;
    });
    return pending;
  }, [
    interfaceLanguage,
    interviewId,
    mode,
    navigate,
    t,
    user?.id,
  ]);

  const {isRegenerating, isReprocessing, refreshError, handleRefresh} = useReviewRefresh({
    interviewId, role: user?.role, mode, isCompleted, recapData, setRecapData, fetchInterview,
  });
  useEffect(() => {
    if (mode === 'review' && isOwner && recapData?.evaluationProcessing?.status === 'complete') {
      window.dispatchEvent(new Event('perception-survey-updated'));
    }
  }, [isOwner, mode, recapData?.evaluationProcessing?.status]);
  const refreshBusy =
    isRegenerating || isReprocessing ||
    [recapData?.evaluationProcessing?.status, recapData?.observationProcessing?.status].some(
      (status) => status === 'queued' || status === 'processing',
    );

  useEffect(() => {
    void fetchInterview();
    return () => {
      interviewRequestRef.current += 1;
      interviewAbortRef.current?.abort();
      interviewReadRef.current = null;
    };
  }, [fetchInterview]);

  useEffect(() => {
    if (interview?.status !== 'processing') return;
    let active = true;
    let timer: number;
    const poll = async () => {
      await fetchInterview();
      if (active) timer = window.setTimeout(() => void poll(), 5000);
    };
    timer = window.setTimeout(() => void poll(), 5000);
    return () => {
 active = false; window.clearTimeout(timer);
};
  }, [interview?.status, fetchInterview]);

  const retryCompletion = async () => {
    if (!interviewId || retryingCompletion) return;
    setRetryingCompletion(true);
    setCompletionRetryError(false);
    try {
      await completeInterview(interviewId.toString());
      await fetchInterview();
    } catch (error) {
      console.error('Failed to retry interview completion:', error);
      setCompletionRetryError(true);
    } finally {
      setRetryingCompletion(false);
    }
  };



  const handleSendMessage = useCallback(
    async (content: string, timing?: SpeechTiming) => {
      const segmentId = recordingRef.current?.segmentId;
      if (interviewId && !endingRef.current && content.trim() && (!segmentId || recordingRef.current?.syncPending)) {
        deferredUtteranceRef.current = {content, timing};
        return;
      }
      if (!interviewId || !segmentId || recordingRef.current?.syncPending || isLoading || sendInFlightRef.current || endingRef.current || !content.trim()) {
        utteranceInFlightRef.current = false;
        return;
      }
      if (pendingMessageRef.current && pendingMessageRef.current.content !== content) {
        // A second utterance arrived while the first is being sent. Show a brief notification.
        console.warn('Utterance ignored: a message is already being sent');
        utteranceInFlightRef.current = false;
        return;
      }
      const retry = Boolean(pendingMessageRef.current);
      const pending = pendingMessageRef.current ?? {content, timing, requestId: utteranceRequestId.current ?? crypto.randomUUID(),
        clockMs: speechStartClockRef.current ?? recordingRef.current?.elapsedAt()};
      speechStartClockRef.current = null;
      utteranceRequestId.current = null;
      if (!retry) measureResponse('transcription', audioSubmittedAtRef.current, pending.requestId);
      pendingMessageRef.current = pending;
      sendInFlightRef.current = true;
      setPatientTurnActive(true);
      const optimisticMessage: Message = {
        id: Date.now(),
        content,
        createdAt: new Date().toISOString(),
        senderType: 'user',
        interviewId,
        senderAvatar: doctorImage,
      };
      if (!retry) setMessages((current) => [...(current || []), optimisticMessage]);
      if (!retry && pending.clockMs != null) setMessageTimes((times) => ({...times, [optimisticMessage.id]: pending.clockMs!}));
      setMessageError(null);
      setIsLoading(true);
      let requestStartedAt: number | undefined;
      try {
        recordingRef.current?.submitStudentTurn(pending.requestId);
        pending.captureTiming ??= await recordingRef.current?.prepareStudentTurn?.(timing);
        await recordingRef.current?.resumeAudioGraph();
        requestStartedAt = performance.now();
        const response = pending.captureTiming
          ? await sendMessage(interviewId.toString(), pending.content, pending.requestId, segmentId, pending.captureTiming)
          : await sendMessage(interviewId.toString(), pending.content, pending.requestId, segmentId);
        measureResponse(retry ? 'reply-retry' : 'reply', requestStartedAt, pending.requestId);
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
        const patientMessage = processedMessages.find(
          (message) => message.senderType !== 'user' && response.newMessageIds.includes(message.id),
        );
        if (patientMessage) {
          responsePlaybackRef.current = {
            messageId: patientMessage.id,
            requestId: pending.requestId,
            submittedAt: audioSubmittedAtRef.current,
            receivedAt: performance.now(),
          };
        } else {
          setPatientTurnActive(false);
          recordingRef.current?.returnFloorToStudent();
        }
        const studentMessage = processedMessages.find(
          (message) => response.newMessageIds.includes(message.id) && message.senderType === 'user',
        );
        if (studentMessage) recordingRef.current?.recordStudentTurn(studentMessage.id);
        if (studentMessage && pending.clockMs != null) setMessageTimes((times) => ({...times, [studentMessage.id]: pending.clockMs!}));
        pendingMessageRef.current = null;
      } catch (error) {
        measureResponse('reply-failed', requestStartedAt, pending.requestId);
        console.error('Failed to send message:', error);
        setPatientTurnActive(false);
        setMessageError(t('clinicalChat.messageSendError'));
        if (interview?.interviewMetadata?.recordingTransport === 'per_turn_v1' &&
            error instanceof Error && 'status' in error && error.status === 409) {
          recordingRef.current?.pause();
          setSimulationAccepted(false);
          setResumePromptOpen(true);
        }
      } finally {
        utteranceInFlightRef.current = false;
        sendInFlightRef.current = false;
        setIsLoading(false);
      }
    },
    [interview?.patientGender, interview?.interviewMetadata?.recordingTransport, interviewId, isLoading, t],
  );

  const speechLanguage =
    interview?.interviewMetadata?.patientResponseLanguage === 'es' ? 'es-ES' : 'en-US';
  const patientHasFloor = patientTurnActive || isLoading || isPatientSpeaking;
  patientFloorRef.current = patientHasFloor;
  const handleUtteranceCommitted = useCallback(() => {
    if (endingRef.current) return;
    utteranceInFlightRef.current = true;
    audioSubmittedAtRef.current = performance.now();
    setPatientTurnActive(true);
    const requestId = crypto.randomUUID();
    utteranceRequestId.current = requestId;
    recordingRef.current?.submitStudentTurn(requestId);
  }, []);
  const handleUtteranceFailed = useCallback(() => {
    utteranceInFlightRef.current = false;
    speechStartClockRef.current = null;
    measureResponse('transcription-failed', audioSubmittedAtRef.current);
    audioSubmittedAtRef.current = undefined;
    utteranceRequestId.current = null;
    setPatientTurnActive(false);
    recordingRef.current?.returnFloorToStudent();
  }, []);
  const handleSpeechStart = useCallback(() => {
    speechStartClockRef.current = recordingRef.current?.elapsedAt() ?? null;
    recordingRef.current?.markSpeechStart();
  }, []);
  const recording = useInterviewRecording({
    missingMessageIds: (interview?.interviewMetadata?.missingEvidenceMessageIds as number[] | undefined) ?? [],
    studentMessageIds: (messages ?? []).filter((message) => message.senderType === 'user').map((message) => message.id),
    patientMessageIds: (messages ?? []).filter((message) => message.senderType !== 'user').map((message) => message.id),
    interviewId: interviewId ?? undefined,
    enabled: Boolean(isSimulationActive && isOwner),
    cameraStream: media.cameraStream,
    microphoneStream: media.microphoneStream,
    microphoneState: media.microphoneState,
    cameraEnabled: media.cameraState === 'ready',
    microphoneEnabled: media.microphoneState === 'ready',
    patientAudioEnabled: audioAutoPlayEnabled,
    patientAvatar: patient.avatar,
    patientName: patient.name,
    resumeAttemptId: freshSessionRef.current.resume?.resumeAttemptId,
    recoveredPatientMessageId: freshSessionRef.current.resume?.recoveredPatientMessageId,
    initialPatientMessageId: initialPatientMessageIdRef.current,
    initialOffsetMs: freshSessionRef.current.resume?.offsetMs,
  });
  recordingRef.current = recording;
  const capturePaused = Boolean(recording.syncPending || (!recording.segmentId && recording.status !== 'failed'));

  // Detect when capture becomes invalidated while a deferred utterance is pending.
  useEffect(() => {
    const deferred = deferredUtteranceRef.current;
    if (deferred && recording.errorCode && ['capture-geometry-changed', 'capture-device-changed', 'temporary-storage-failed',
      'capture-superseded', 'capture-closed'].includes(recording.errorCode)) {
      setLostDeferredUtterance(deferred.content);
      deferredUtteranceRef.current = null;
    }
  }, [recording.errorCode]);

  const speech = useHandsFreeSpeech({
    language: speechLanguage,
    interviewId: interviewId ? Number(interviewId) : undefined,
    paused: patientHasFloor || capturePaused || Boolean(messageError),
    disabled: !isSimulationActive || !isOwner || isCompleted || (ending && !patientHasFloor),
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

  // The server stopped accepting this capture. Another window continued the session: offer the resume flow (the same
  // as a rejected message does). The interview or recording already ended: reload what the server now says about it.
  useEffect(() => {
    if (mode !== 'session') return;
    if (recording.errorCode === 'capture-superseded') {
      speech.stop();
      recording.pause();
      setSimulationAccepted(false);
      setResumePromptOpen(true);
    } else if (recording.errorCode === 'capture-closed') {
      speech.stop();
      void fetchInterview();
    }
  }, [recording.errorCode]);

  useEffect(() => {
    const deferred = deferredUtteranceRef.current;
    if (deferred && isSimulationActive && recording.segmentId && !recording.syncPending && !isLoading) {
      deferredUtteranceRef.current = null;
      void handleSendMessage(deferred.content, deferred.timing);
    }
  }, [isSimulationActive, recording.segmentId, recording.syncPending, isLoading, handleSendMessage]);

  const handlePatientSpeakingChange = useCallback((speaking: boolean) => {
    if (speaking) patientFloorRef.current = true;
    setIsPatientSpeaking(speaking);
  }, []);
  const handlePatientTurnStart = useCallback((messageId: number) => {
    patientFloorRef.current = true;
    const response = responsePlaybackRef.current;
    if (response?.messageId === messageId) {
      measureResponse('audio-start', response.receivedAt, response.requestId);
      measureResponse('total-to-playing', response.submittedAt, response.requestId);
      response.startedAt = performance.now();
    }
    recording.beginPatientTurn(messageId);
    setMessageTimes((times) => ({...times, [messageId]: recording.elapsedAt()}));
  }, [recording.beginPatientTurn, recording.elapsedAt]);

  const handlePatientTurnEnd = useCallback((messageId: number, playbackComplete: boolean, continuous?: boolean) => {
    const response = responsePlaybackRef.current;
    if (response?.messageId === messageId) {
      measureResponse(playbackComplete ? 'audio-finished' : 'audio-interrupted', response.startedAt, response.requestId);
      responsePlaybackRef.current = null;
    }
    recording.endPatientTurn(messageId, playbackComplete, performance.now(), continuous);
  }, [recording.endPatientTurn]);

  const handlePatientTurnComplete = useCallback((messageId: number) => {
    const response = responsePlaybackRef.current;
    if (response?.messageId === messageId) {
      measureResponse('audio-failed-before-start', response.receivedAt, response.requestId);
      responsePlaybackRef.current = null;
    }
    setPatientTurnActive(false);
  }, []);

  useEffect(() => {
    if (!isSimulationActive) {
      setElapsedSeconds(0);
      return undefined;
    }
    const updateElapsedTime = () => {
      setElapsedSeconds(Math.max(0, Math.floor(recording.elapsedAt() / 1000)));
    };
    updateElapsedTime();
    const timer = window.setInterval(updateElapsedTime, 1000);
    return () => window.clearInterval(timer);
  }, [isSimulationActive, recording.elapsedAt]);
  const conversationPhase: 'student' | 'sending' | 'patient' | 'paused' | 'finalizing' = ending ? 'finalizing'
    : capturePaused || messageError ? 'paused'
      : isLoading || speech.isSubmittingUtterance ? 'sending' : patientHasFloor ? 'patient' : 'student';
  const isEndInterviewDisabled = !isSimulationActive || !isOwner || isCompleted || conversationPhase !== 'student'
    || (!recording.segmentId && recording.status !== 'failed');

  const sealCapture = async () => {
    setSealingCapture(true);
    try {
      const sealed = await recording.sealForEnding();
      setCaptureSealed(sealed);
      setElapsedSeconds(Math.floor(recording.elapsedAt() / 1000));
      return sealed;
    } finally {
      setSealingCapture(false);
    }
  };

  const handleEndInterview = () => {
    if (isEndInterviewDisabled || endingRef.current || patientFloorRef.current || utteranceInFlightRef.current || sendInFlightRef.current) return;
    endingRef.current = true;
    speech.stop();
    setCaptureSealed(false);
    setEnding(true);
    void sealCapture();
  };

  const prepareResumption = async (id: number) => {
    resumeRequestRef.current ??= crypto.randomUUID();
    await recording.stopForRecovery();
    return resumeTurnInterview(id, resumeRequestRef.current);
  };

  const handleResume = async () => {
    if (!interviewId || forcingTerminationRef.current) return;
    forcingTerminationRef.current = true;
    setResumingInterview(true);
    setForceTerminationError(false);
    try {
      const resume = await prepareResumption(interviewId);
      navigate(ROUTES.calibration, {replace: true, state: {draftInterviewId: interviewId, resume}});
    } catch (error) {
      console.error('Interview resume preparation failed:', error);
      setForceTerminationError(true);
    } finally {
      forcingTerminationRef.current = false;
      setResumingInterview(false);
    }
  };

  const handleForceTermination = async () => {
    if (!interviewId || forcingTerminationRef.current) return;
    forcingTerminationRef.current = true;
    setForcingTermination(true);
    setForceTerminationError(false);
    try {
      const forceSignal = AbortSignal.timeout(30_000);
      let resumeAttemptId: string | undefined;
      if (resumePromptOpen) {
        resumeRequestRef.current ??= crypto.randomUUID();
        await recording.stopForRecovery();
        resumeAttemptId = (await resumeTurnInterview(interviewId, resumeRequestRef.current, true, forceSignal)).resumeAttemptId;
      } else if (!await recording.finalize(true)) {
        throw new Error('Recording preservation failed; retry before leaving the interview');
      }
      await interruptInterview(String(interviewId), {...(resumeAttemptId
        ? {resumeAttemptId} : {segmentId: recording.captureSegmentId}),
      signal: forceSignal});
      // An interrupted interview has no review; return to the history.
      navigate(ROUTES.interviews, {replace: true});
    } catch (error) {
      console.error('Failed to force interview termination:', error);
      setForceTerminationError(true);
      setForcingTermination(false);
      forcingTerminationRef.current = false;
    }
  };
  const cancelHypotheses = async () => {
    if (resumingInterview) return;
    if (!captureSealed && !await sealCapture()) return;
    if (!recording.canRestartWithCurrentGeometry()) {
      void handleResume();
      return;
    }
    await recording.restartAfterCancel();
    setCaptureSealed(false);
    endingRef.current = false;
    setEnding(false);
    // Opening the dialog stopped speech recognition; the new capture needs it again for the voice bubble and transcription.
    speech.start();
  };
  const handleInterviewFinalized = (nextEvaluationData: InterviewEvaluationResponse) => {
    setInterview((current) => current ? {
      ...current,
      ...nextEvaluationData.interview,
      isOwner: current.isOwner,
      reviewAccess: current.isOwner && user?.role !== 'admin'
        ? {canViewAssessments: false, assignmentId: null, selfAssessmentRequired: true}
        : current.reviewAccess,
    } : nextEvaluationData.interview);
    setSimulationAccepted(false);
    setEnding(false);
    setHypothesesSubmitted(true);
    if (interviewId) navigate(interviewPath(interviewId, 'review'), {replace: true});
  };

  if (!interviewId) return null;
  if (!interview) {
    if (!interviewLoadError) return <InterviewContentLoading />;
    return (
      <div className="p-layout" role={interviewLoadError ? 'alert' : 'status'}>
        <p>{t(interviewLoadError ? 'clinicalChat.loadError' : 'common.loading')}</p>
        {interviewLoadError && <button className="ui-button ui-button--primary" onClick={() => void fetchInterview()} disabled={interviewLoading}>{t('common.retry')}</button>}
      </div>
    );
  }

  if (mode === 'session' && (isTerminal || interview.status === 'processing' || captureFinalized || canRetryCompletion)) {
    return <Navigate to={isCompleted || interview.status === 'processing' || canRetryCompletion ? interviewPath(interviewId, 'review') : ROUTES.interviews} replace />;
  }
  if (mode === 'review' && canRetryCompletion) {
    return <div className="p-layout" role="status">
      <p>{t(canRetryCompletion ? 'clinicalChat.completionRecovery' : 'clinicalChat.processing')}</p>
      {canRetryCompletion && isOwner && <button type="button" className="ui-button ui-button--primary" disabled={retryingCompletion} onClick={() => void retryCompletion()}>{t('common.retry')}</button>}
      {(completionRetryError || interviewLoadError) && <p role="alert">{t('clinicalChat.completionRetryError')}</p>}
    </div>;
  }
  if (mode === 'review' && !isCompleted && interview.status !== 'processing') {
    return <Navigate to={ROUTES.interviews} replace />;
  }

  const InterviewLayout = isInterviewOpen ? ActiveSimulationLayout : SimulationResultsLayout;
  const assessments = (
    <>
      {mode === 'review' && interview.reviewAccess?.canViewAssessments !== false && (
        <AssessmentSelector
          canAssignDoctors={mode === 'review' && user?.role === 'admin' && interview.reviewAccess?.canAssignDoctors}
          evaluationData={evaluationData ?? {interview, evaluationResults: [], multimodalEvaluationResults: []}}
          isLoading={interview.status === 'processing'}
          className="md:max-xl:col-start-2 md:max-xl:row-start-2 xl:col-start-3 xl:row-start-1"
          canRegenerate={mode === 'review' && user?.role === 'admin' && isCompleted}
          evaluationStale={recapData?.evaluationProcessing?.status === 'stale'}
          isRegenerating={isRegenerating}
          onRegenerate={() => void handleRefresh(false)}
          onReprocess={mode === 'review' && isCompleted ? () => void handleRefresh(true) : undefined}
          isReprocessing={isReprocessing}
          refreshDisabled={refreshBusy}
          turns={recapData?.turns}
          onJumpToTurn={(turnId) => setSeekRequest((previous) => ({
            turnId,
            requestId: (previous?.requestId ?? 0) + 1,
          }))}
        />
      )}
      {mode === 'review' &&
        interview.reviewAccess?.canViewAssessments === false &&
        (interview.reviewAccess.assignmentId || interview.reviewAccess.selfAssessmentRequired) && (
          <HumanRatingPanel
            interview={interview}
            assignmentId={interview.reviewAccess.selfAssessmentRequired ? undefined : interview.reviewAccess.assignmentId ?? undefined}
            selfInterviewId={interview.reviewAccess.selfAssessmentRequired ? interviewId : undefined}
            onSubmitted={() => void fetchInterview()}
          />
        )}
    </>
  );

  return (
    <InterviewLayout documentScroll={mode === 'review'}>
      {!isInterviewOpen && (
        <aside className={`flex min-h-0 min-w-0 flex-col ${mode === 'review' ? 'review-information self-start' : 'xl:col-start-1 xl:row-start-1 md:max-xl:col-start-1 md:max-xl:row-start-2'}`}>
          <PatientProfile
            patient={patient}
            isReview={mode === 'review'}
            caseTitle={interview.clinicalCase?.title}
            personality={interview.personality}
            headerAction={mode === 'review' && user?.role === 'admin' ? <CalibrationReferenceDialog key={interviewId} interviewId={interviewId} /> : undefined}
          >
            {mode === 'review' && (
              <>
                {refreshError && (
                  <p role="alert" className="p-inset text-danger-700 default-text">
                    {t('evaluation.refreshFailed')}
                  </p>
                )}
                <InterviewRecap
                  interviewId={interviewId}
                  messages={messages}
                  patientName={patient.name}
                  patientAvatar={patient.avatar}
                  infoDisabled={
                    interview.reviewAccess?.canViewAssessments === false ||
                    isReprocessing ||
                    ['queued', 'processing'].includes(recapData?.observationProcessing?.status ?? '')
                  }
                  onRecapLoaded={setRecapData}
                  refreshedRecap={recapData}
                  refreshInProgress={isRegenerating || isReprocessing}
                  seekRequest={seekRequest}
                />
              </>
            )}
          </PatientProfile>
        </aside>
      )}
      {isInterviewOpen && !resumePromptOpen && (
        <CallStage
          className="md:col-start-1 md:row-start-1"
          patientAvatar={patient.avatar}
          patientName={patient.name}
          studentName={studentName}
          patientSpeaking={isPatientSpeaking}
          cameraStream={media.cameraStream}
          cameraEnabled={media.cameraState === 'ready'}
          cameraStarting={media.cameraState === 'loading'}
          cameraErrorCode={
            ['permission-denied', 'unavailable', 'unsupported'].includes(media.cameraState)
              ? media.cameraState
              : null
          }
          onRetryCamera={() => void media.startCamera()}
        />
      )}

      {mode !== 'review' && !resumePromptOpen && (
        <div className={isInterviewOpen ? 'flex min-h-0 min-w-0 flex-col gap-layout md:col-start-2 md:row-start-1' : 'contents'}>
          <section
            className={`ui-panel flex min-w-0 flex-1 flex-col overflow-hidden xl:col-start-2 xl:row-start-1 ${isInterviewOpen ? 'min-h-80 md:min-h-0' : 'md:max-xl:col-span-2 md:max-xl:row-start-1 xl:h-full'}`}
          >
            <ConversationTranscript
              headerAction={isInterviewOpen ? <CallTimer elapsedSeconds={elapsedSeconds} /> : undefined}
              interviewId={interviewId}
              messageTimes={messageTimes}
              messages={isSimulationActive ? messages : []}
              isListening={speech.isListening && conversationPhase === 'student'}
              capturePaused={conversationPhase === 'paused'}
              audioLevel={speech.audioLevel}
              patientAudioLevel={recording.patientAudioLevel}
              hasPendingUtterance={speech.hasPendingUtterance}
              isSubmittingUtterance={speech.isSubmittingUtterance}
              onSubmitUtterance={() => {
                if (!endingRef.current && conversationPhase === 'student' && recording.segmentId) speech.submitUtterance();
              }}
              isLoading={isLoading}
              audioAutoPlayEnabled={audioAutoPlayEnabled}
              preparedAudio={preparedAudioRef.current}
              playbackReady={isSimulationActive && recording.isCapturing && !recording.syncPending}
              onPatientSpeakingChange={handlePatientSpeakingChange}
              onPatientTurnPrepare={recording.preparePatientTurn}
              captureEnabled={recording.isCapturing}
              routePatientAudio={recording.routePatientAudio}
              resumeAudioGraph={recording.resumeAudioGraph}
              onPatientTurnStart={handlePatientTurnStart}
              onPatientTurnEnd={handlePatientTurnEnd}
              onPatientTurnComplete={handlePatientTurnComplete}
            />
            {(speech.errorCode || messageError) && (
              <div
                className="ui-notice ui-notice--warning mx-layout mb-layout text-left"
                role="alert"
              >
                {messageError || t(`clinicalChat.call.speechErrors.${speech.errorCode}`)}
                {messageError && <button type="button" className="ui-button ui-button--secondary" disabled={isLoading} onClick={() => {
                  const pending = pendingMessageRef.current;
                  if (pending) void handleSendMessage(pending.content, pending.timing);
                }}>{t('common.retry')}</button>}
              </div>
            )}
            {recording.syncPending && (recording.errorCode || !navigator.onLine || recording.reconnecting) && <div className="mx-layout mb-layout text-warning-800 secondary-text" role="status">
              <p>{!navigator.onLine ? t('clinicalChat.syncPausedOffline')
                : recording.reconnecting && !recording.errorCode ? t('clinicalChat.syncReconnecting') : t('clinicalChat.syncPaused')}</p>
              <button type="button" className="ui-button ui-button--secondary" onClick={() => {
                speech.stop();
                recording.pause();
                setResumePromptOpen(true);
              }}>{t('clinicalChat.reviewSession')}</button>
            </div>}
            {lostDeferredUtterance && (
              <div
                className="ui-notice ui-notice--warning mx-layout mb-layout text-left"
                role="alert"
              >
                {t('clinicalChat.lostDeferredUtterance', {content: lostDeferredUtterance})}
                <button type="button" className="ui-button ui-button--secondary" onClick={() => {
                  setLostDeferredUtterance(null);
                  void handleSendMessage(lostDeferredUtterance);
                }}>{t('clinicalChat.retryLostUtterance')}</button>
              </div>
            )}
            {recording.errorCode && (
              <div
                className="ui-notice ui-notice--warning mx-layout mb-layout text-left"
                role="alert"
              >
                {t(`clinicalChat.recording.errors.${recording.errorCode}`)}
                {recording.canRetryStart && <button type="button" className="ui-button ui-button--secondary"
                  onClick={recording.retryStart}>{t('common.retry')}</button>}
                {recording.errorCode === 'temporary-storage-failed' && <button type="button" className="ui-button ui-button--secondary"
                  onClick={async () => {
                    const recovered = await recording.attemptStorageRecovery();
                    if (!recovered) setResumePromptOpen(true);
                  }}>{t('common.retry')}</button>}
                {['finalize-timeout', 'finalize-failed'].includes(recording.errorCode) && (
                  <button type="button" className="ui-button ui-button--secondary"
                    onClick={() => void recording.finalize()}>{t('common.retry')}</button>
                )}
              </div>
            )}
            {!isOwner && (
              <div className="ui-panel-footer text-center text-neutral-500 default-text">
                {t('clinicalChat.readOnlyMode')}
              </div>
            )}
            {isInterviewOpen && <CallToolbar endDisabled={isEndInterviewDisabled} onEndInterview={handleEndInterview} />}
          </section>
        </div>
      )}

      {mode === 'review' ? (
        <div className="review-assessments flex min-h-0 min-w-0 flex-col self-start">
          {assessments}
        </div>
      ) : null}

      <Modal
        size="small"
        open={ending && !hypothesesSubmitted}
        closeAction={cancelHypotheses}
        closeOnOutsideClick={false}
        hasActions
        ariaLabel={t('clinicalChat.clinicalHypotheses')}
      >
        <ClinicalHypotheses
          captureSegmentId={recording.captureSegmentId}
          onCancel={cancelHypotheses}
          canCancel={!resumingInterview}
          preparingCapture={sealingCapture || resumingInterview}
          recordingError={recording.errorCode ? t(`clinicalChat.recording.errors.${recording.errorCode}`) : undefined}
          beforeComplete={async (onProgress) => (captureSealed || await sealCapture()) && recording.finalize(false, onProgress)}
          waitingForTurn={patientHasFloor}
          onCompleted={handleInterviewFinalized}
        />
      </Modal>
      <WelcomeModal
        isOpen={openWelcomeModal}
        busy={acceptingWelcome}
        error={welcomeError}
        onAccept={() => {
          if (!interviewId || acceptingWelcomeRef.current) return;
          acceptingWelcomeRef.current = true;
          preparedAudioRef.current ??= preparePatientAudio();
          void recording.resumeAudioGraph().catch(() => undefined);
          setAcceptingWelcome(true);
          setWelcomeError(false);
          void (async () => {
            try {
              if (!interview.startTime) await startInterview(interviewId);
              const refreshed = await fetchInterview();
              if (!refreshed?.startTime) throw new Error('Interview start could not be confirmed');
              setSimulationAccepted(true);
              setOpenWelcomeModal(false);
            } catch {
              setWelcomeError(true);
            } finally {
              acceptingWelcomeRef.current = false;
              setAcceptingWelcome(false);
            }
          })();
        }}
        onCancel={() => navigate(ROUTES.calibration, {replace: true, state: {draftInterviewId: Number(interviewId)}})}
      />
      <ResumeSessionDialog
        open={resumePromptOpen}
        forcingTermination={forcingTermination}
        resumingInterview={resumingInterview}
        forceTerminationError={forceTerminationError}
        onResume={() => void handleResume()}
        onForceTermination={() => void handleForceTermination()}
      />
    </InterviewLayout>
  );
};
