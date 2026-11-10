import {previewAudioUrl, supportsProgressiveAudio} from '../../services/speech/previewAudioUrl';
import {useCallback, useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Navigate, useLocation, useNavigate} from 'react-router-dom';
import {useUser} from '../../hooks/useUser';
import {getAuthHeaders} from '../../services/auth/authHeaders';
import {apiFetch} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';
import {ROUTES, type CalibrationRouteState} from '../../utils/routes';
import {Message} from '../../types';
import {ActiveSimulationLayout} from '../ClinicalChat/InterviewLayouts';
import {ClinicalHypotheses} from '../ClinicalChat/ClinicalHypotheses';
import {Modal} from '../common/Modal';
import {CallStage} from '../ClinicalChat/CallStage';
import {CallTimer, CallToolbar} from '../ClinicalChat/CallToolbar';
import {useHandsFreeSpeech} from '../../hooks/useHandsFreeSpeech';
import {useInterviewMedia} from '../../contexts/interviewMedia';
import {ConversationTranscript} from '../ClinicalChat/ConversationTranscript';
import {preparePatientAudio} from '../../services/speech/preparePatientAudio';
import {getPatientImage} from '../ClinicalChat/helpers';
import {WelcomeModal} from '../ClinicalChat/WelcomeModal';

type PreviewConfiguration = CalibrationRouteState & {
  patientName?: string | null;
};

export const PatientPreview = () => {
  const {user, isLoading} = useUser();
  const {t} = useTranslation();
  const navigate = useNavigate();
  const configuration = useLocation().state as PreviewConfiguration | null;
  const [exchanges, setExchanges] = useState<{question: string; answer: string}[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState(false);
  const [pending, setPending] = useState(false);
  const [patientHasFloor, setPatientHasFloor] = useState(false);
  const [patientSpeaking, setPatientSpeaking] = useState(false);
  const [patientAudioLevel, setPatientAudioLevel] = useState(0);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const preparedAudioRef = useRef<HTMLAudioElement | null>(null);
  const disposeMeterRef = useRef<(() => void) | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<Message | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [ending, setEnding] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const isSuperuser = user?.role === 'superuser';
  const isConfigured = Boolean(isSuperuser && configuration?.clinicalCaseId
    && configuration.personalityId && configuration.gender);
  const {cameraStream, cameraState, microphoneStream, microphoneState, startCamera, startMicrophone, stopAll} = useInterviewMedia();

  const stopMeter = useCallback(() => {
    disposeMeterRef.current?.();
    disposeMeterRef.current = null;
  }, []);

  useEffect(() => () => {
    stopMeter();
    const context = playbackContextRef.current;
    playbackContextRef.current = null;
    if (context) void context.close().catch(() => undefined);
  }, [stopMeter]);

  const routePatientAudio = useCallback((audio: HTMLAudioElement) => {
    const context = playbackContextRef.current;
    if (context?.state !== 'running') return false;
    stopMeter();
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    const samples = new Float32Array(analyser.fftSize);
    const source = context.createMediaElementSource(audio);
    source.connect(analyser);
    analyser.connect(context.destination);
    const timer = window.setInterval(() => {
      analyser.getFloatTimeDomainData(samples);
      const rms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length);
      setPatientAudioLevel(Math.min(1, rms / 0.16));
    }, 60);
    disposeMeterRef.current = () => {
      window.clearInterval(timer);
      source.disconnect();
      analyser.disconnect();
    };
    return true;
  }, [stopMeter]);

  useEffect(() => {
    if (!isConfigured || startedAt === null) return;
    void Promise.all([startCamera(), startMicrophone()]);
    return stopAll;
  }, [isConfigured, startedAt, startCamera, startMicrophone, stopAll]);


  useEffect(() => {
    if (startedAt === null) return;
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  const submit = async (submittedQuestion: string) => {
    if (!isSuperuser || !configuration || pending || !submittedQuestion) return;
    const question: Message = {
      id: messages.length + 1,
      interviewId: 0,
      senderType: 'user',
      content: submittedQuestion,
      createdAt: new Date().toISOString(),
    };
    setPendingQuestion(question);
    setPending(true);
    setError(false);
    try {
      const response = await apiFetch(`${API_URL}/clinical-cases/${configuration.clinicalCaseId}/patient-preview`, {
        method: 'POST',
        headers: {...getAuthHeaders(), 'Content-Type': 'application/json'},
        body: JSON.stringify({
          question: submittedQuestion,
          language: configuration.patientResponseLanguage,
          gender: configuration.gender,
          personality_id: configuration.personalityId,
          history: exchanges.slice(-12),
        }),
      });
      if (!response.ok) throw new Error('Patient preview failed');
      const result: {answer: string} = await response.json();
      setExchanges((previous) => [...previous, {question: submittedQuestion, answer: result.answer}]);
      setMessages((previous) => [...previous, question, {
        id: question.id + 1,
        interviewId: 0,
        senderType: 'patient',
        content: result.answer,
        createdAt: new Date().toISOString(),
        messageMetadata: {isNew: true},
      }]);
      setPatientHasFloor(true);
      setPendingQuestion(null);
    } catch {
      setError(true);
    } finally {
      setPending(false);
    }
  };

  const speech = useHandsFreeSpeech({
    language: configuration?.patientResponseLanguage ?? 'es',
    disabled: startedAt === null || ending || !isConfigured || microphoneState !== 'ready',
    autoStart: true,
    paused: pending || patientHasFloor,
    microphoneStream,
    onUtterance: submit,
  });
  const submitUtterance = () => {
    if (window.AudioContext) {
      try {
        playbackContextRef.current ??= new AudioContext();
        void playbackContextRef.current.resume().catch(() => undefined);
      } catch {
        // The native audio element can still play without a level meter.
      }
    }
    speech.submitUtterance();
  };

  const completePatientTurn = () => {
    if (!preparedAudioRef.current) stopMeter();
    setPatientAudioLevel(0);
    setPatientHasFloor(false);
  };

  const cameraError = cameraState === 'permission-denied' || cameraState === 'unavailable'
    || cameraState === 'unsupported' ? cameraState : null;
  const microphoneError = microphoneState !== 'idle' && microphoneState !== 'loading'
    && microphoneState !== 'ready';

  if (isLoading) return <div role="status">{t('common.loading')}</div>;
  if (!isSuperuser || !configuration?.clinicalCaseId || !configuration.personalityId
    || !configuration.gender) return <Navigate to={ROUTES.clinicalCases} replace />;

  const loadPatientAudio = async (message: Message, signal: AbortSignal) => {
    const progressive = supportsProgressiveAudio();
    const response = await apiFetch(`${API_URL}/clinical-cases/${configuration.clinicalCaseId}/patient-preview/speech?progressive=${progressive}`, {
      method: 'POST',
      headers: {...getAuthHeaders(), 'Content-Type': 'application/json'},
      body: JSON.stringify({text: message.content, gender: configuration.gender, personality_id: configuration.personalityId}),
      signal,
    });
    if (!response.ok) throw new Error('Patient preview audio is unavailable');
    return previewAudioUrl(response, signal, progressive);
  };

  const patient = {
    name: configuration.patientName || t('clinicalChat.call.patient'),
    avatar: getPatientImage(configuration.gender),
  };

  return (
    <ActiveSimulationLayout>
      <CallStage className="md:col-start-1 md:row-start-1"
        patientAvatar={patient.avatar} patientName={patient.name}
        studentName={user?.name?.trim() || t('clinicalChat.call.student')}
        patientSpeaking={patientSpeaking} cameraStream={cameraStream} cameraEnabled={cameraState === 'ready'}
        cameraStarting={cameraState === 'loading'} cameraErrorCode={cameraError}
        onRetryCamera={() => void startCamera()} />
      <div className="flex min-h-0 min-w-0 flex-col gap-layout md:col-start-2 md:row-start-1">
        <section className="ui-panel flex min-h-80 min-w-0 flex-1 flex-col overflow-hidden md:min-h-0">
          <ConversationTranscript headerAction={<CallTimer elapsedSeconds={elapsedSeconds} />} interviewId={0} startedAt={startedAt ?? undefined} messages={pendingQuestion ? [...messages, pendingQuestion] : messages}
            isListening={speech.isListening && !patientHasFloor} audioLevel={speech.audioLevel}
            patientAudioLevel={patientAudioLevel} routePatientAudio={routePatientAudio}
            hasPendingUtterance={speech.hasPendingUtterance}
            isSubmittingUtterance={speech.isSubmittingUtterance && !patientHasFloor}
            onSubmitUtterance={submitUtterance} isLoading={pending}
            audioAutoPlayEnabled playbackReady={startedAt !== null && microphoneState === 'ready' && cameraState === 'ready'} loadPatientAudio={loadPatientAudio}
            preparedAudio={preparedAudioRef.current}
            onPatientSpeakingChange={setPatientSpeaking} onPatientTurnComplete={completePatientTurn} />
          {(speech.errorCode || microphoneError) && (
            <p role="alert" className="ui-notice ui-notice--warning mx-layout mb-layout">
              {t(`clinicalChat.call.speechErrors.${speech.errorCode ?? (microphoneState === 'permission-denied' ? 'not-allowed' : 'audio-capture')}`)}
              {microphoneError && <button type="button" className="ui-button ui-button--secondary"
                onClick={() => void startMicrophone()}>{t('common.retry')}</button>}
            </p>
          )}
          {error && pendingQuestion && (
            <div className="ui-notice ui-notice--warning mx-layout mb-layout text-left" role="alert">
              {t('patientPreview.error')}
              <button type="button" className="ui-button ui-button--secondary" onClick={() => void submit(pendingQuestion.content)}>
                {t('common.retry')}
              </button>
            </div>
          )}
          <CallToolbar endDisabled={startedAt === null} onEndInterview={() => setEnding(true)} />
        </section>
      </div>
      <WelcomeModal isOpen={startedAt === null} onCancel={() => navigate(ROUTES.clinicalCases, {replace: true})}
        onAccept={() => {
          preparedAudioRef.current = preparePatientAudio();
          if (preparedAudioRef.current && window.AudioContext) {
            playbackContextRef.current ??= new AudioContext();
            void playbackContextRef.current.resume().catch(() => undefined);
          }
          const now = Date.now();
          setStartedAt(now);
          setPatientHasFloor(true);
          setMessages([{
            id: 1, interviewId: 0, senderType: 'patient',
            content: configuration.patientResponseLanguage === 'es' ? 'Hola, mucho gusto.' : 'Hello, nice to meet you.',
            createdAt: new Date(now).toISOString(), messageMetadata: {isNew: true},
          }]);
        }} />
      <Modal
        open={ending}
        size="small"
        closeAction={() => setEnding(false)}
        closeOnOutsideClick={false}
        hasActions
        ariaLabel={t('clinicalChat.clinicalHypotheses')}
      >
        <ClinicalHypotheses
          onCancel={() => setEnding(false)}
          onDemoSubmit={() => navigate(ROUTES.clinicalCases, {replace: true})}
        />
      </Modal>
    </ActiveSimulationLayout>
  );
};
