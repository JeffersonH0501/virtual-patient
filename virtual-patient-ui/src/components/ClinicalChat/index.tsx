import {FC, useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {PatientProfile} from './PatientProfile';
import {NotesSection} from './NotesSection';
import {Modal, ChatInput} from '../common';
import {EndInterviewConfirmation} from './EndInterviewConfirmation';
import {ChatInterface} from '../Chats/ChatDetail/ChatInterface';
import {Message} from '../../types/message';
import {ClinicalHypotheses} from './ClinicalHypotheses';
import {WelcomeModal} from './WelcomeModal';
import {TeacherFeedbackSection} from './TeacherFeedbackSection';
import {sendMessage, createSummary} from '../../services/interviews';
import {useParams} from 'react-router-dom';
import {CompleteInterviewResponse} from '../../types/interview';
import {getInterview} from '../../services/interviews/getInterview';
import {Patient} from '../../types/patient';
import {InterviewEvaluationResponse} from '../../types/evaluation';
import {EvaluationResultsModal} from '../Evaluation';
import {getSessionNote, updateSessionNote} from '../../services/sessionNote';
import {getPatientImage, processMessagesWithAvatars, processSummaryData} from './helpers';
import doctorImage from '../../assets/doctor.png';
import patientImageM from '../../assets/patient_m.png';

export const ClinicalChat: FC = () => {
  const {t, i18n} = useTranslation();
  const [feedback, setFeedback] = useState('');
  const [ending, setEnding] = useState(false);
  const [openEndConfirmationModal, setOpenEndConfirmationModal] = useState(false);
  const [openEvaluationModal, setOpenEvaluationModal] = useState(false);
  const [openWelcomeModal, setOpenWelcomeModal] = useState(false);
  const [evaluationData, setEvaluationData] = useState<InterviewEvaluationResponse | null>(null);
  const [audioAutoPlayEnabled, setAudioAutoPlayEnabled] = useState(true);
  const [hypothesesSubmitted, setHypothesesSubmitted] = useState(false);
  const [submittedHypotheses, setSubmittedHypotheses] = useState<
    {
      id: number;
      hypothesisText: string;
      hypothesisOrder: number;
    }[]
  >([]);

  const [messages, setMessages] = useState<Message[]>();
  const [isLoading, setIsLoading] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);
  const {interviewId: interviewIdParam} = useParams<{interviewId: string}>();
  const interviewId = interviewIdParam ? parseInt(interviewIdParam, 10) : null;
  const [interview, setInterview] = useState<CompleteInterviewResponse>();

  // Use isOwner field from API response
  const isOwner = interview?.isOwner ?? false;
  // Calculate if the button should be disabled
  const isEndInterviewDisabled = !isOwner || interview?.status === 'completed';

  const [patient, setPatient] = useState<Patient>({
    name: '',
    id: '',
    avatar: patientImageM, // Default to male image
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
    summary: '',
  });

  const fetchInterview = async () => {
    if (!interviewId) return;

    const interviewData = await getInterview(interviewId.toString());
    setInterview(interviewData);

    // Set messages from interview response with proper avatars
    setMessages(processMessagesWithAvatars(interviewData.messages, interviewData.patientGender));

    // Initialize patient data from interview patient fields
    setPatient((prevPatient) => ({
      ...prevPatient,
      name: interviewData.patientName || 'John Doe',
      id: interviewData.clinicalCase?.id.toString() || 'unknown',
      avatar:
        interviewData.patientPhoto || getPatientImage(interviewData.patientGender || undefined),
      basicInfo: {
        age: interviewData.clinicalCase?.age || 0,
        gender: interviewData.patientGender || 'Unknown',
        bloodType: '', // Not available in clinical case data
        weight: interviewData.clinicalCase?.weightInKg
          ? `${interviewData.clinicalCase.weightInKg} kg`
          : 'Not specified',
      },
    }));

    // Process progress summary if it exists in the response
    if (interviewData.progressSummary) {
      setPatient(processSummaryData(interviewData.progressSummary));
    }

    // Set evaluation data if interview is completed and has evaluation
    if (interviewData.status === 'completed' && interviewData.interviewEvaluation) {
      setEvaluationData({
        interview: {
          id: interviewData.id,
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

    // Set submitted hypotheses if they exist
    if (interviewData.hypotheses && interviewData.hypotheses.length > 0) {
      setSubmittedHypotheses(interviewData.hypotheses);
      setHypothesesSubmitted(true);
    }

    // Load session note
    try {
      const sessionNote = await getSessionNote(interviewId.toString());
      if (sessionNote) {
        setFeedback(sessionNote.notesContent);
      }
    } catch (error) {
      console.error('Failed to load session note:', error);
    }

    if (interviewData.messages?.length === 0 && interviewData.isOwner) {
      setOpenWelcomeModal(true);
    }
  };

  useEffect(() => {
    fetchInterview();
  }, [interviewId]);

  useEffect(() => {
    if (!interviewId || !interview || interview.status === 'completed') return;

    const fetchSummary = () => fetchAndProcessSummary('periodic summary');
    fetchSummary();

    // Set up interval to fetch summary every 40 seconds
    const interval = setInterval(fetchSummary, 40000);

    return () => clearInterval(interval);
  }, [interviewId, interview?.status]);

  // Save session note when user clicks out of the text box
  const handleFeedbackBlur = async () => {
    if (!interviewId || !feedback.trim()) return;

    try {
      await updateSessionNote(interviewId.toString(), {
        notesContent: feedback,
      });
    } catch (error) {
      console.error('Failed to save session note:', error);
    }
  };

  const fetchAndProcessSummary = async (context: string = 'summary') => {
    if (!interviewId) return;

    try {
      const summaryResponse = await createSummary(interviewId.toString());
      if (summaryResponse.summary_result) {
        setPatient(processSummaryData(summaryResponse.summary_result));
      } else {
        console.warn(`${context}: Summary not available yet`);
      }
    } catch (error) {
      console.error(`Failed to fetch ${context}:`, error);
    }
  };

  const handleSendMessage = async (content: string) => {
    if (!interviewId || isLoading) return;

    // Create the user message immediately
    const userMessage: Message = {
      id: Date.now(),
      content,
      createdAt: new Date().toISOString(),
      senderType: 'user',
      interviewId: interviewId,
      senderAvatar: doctorImage,
    };

    // Add user message to the conversation immediately
    setMessages((prev) => (prev ? [...prev, userMessage] : [userMessage]));

    setMessageError(null);
    setIsLoading(true);
    try {
      const response = await sendMessage(interviewId.toString(), content);
      // Set messages from the response with proper avatars
      const processedMessages = processMessagesWithAvatars(
        response.messages,
        interview?.patientGender,
      );
      setMessages(processedMessages);
      // add new message flag to the new messages
      processedMessages.forEach((message) => {
        if (response.newMessageIds.includes(message.id)) {
          message.messageMetadata = {
            isNew: true,
          };
        }
      });
      setMessages(processedMessages);
    } catch (error) {
      console.error('Failed to send message:', error);
      setMessageError(t('clinicalChat.messageSendError'));
    } finally {
      setIsLoading(false);
    }
  };

  const close = () => {
    setOpenEndConfirmationModal(false);
  };

  const handleEndInterview = () => {
    // Only allow ending interview if user is the owner
    if (!isOwner) {
      console.warn('Cannot end interview: User is not the owner');
      return;
    }
    setOpenEndConfirmationModal(true);
  };

  const confirmEnding = async () => {
    setOpenEndConfirmationModal(false);

    // Set ending state immediately so the hypothesis form shows up right away
    setEnding(true);

    // Call createSummary in the background without blocking the UI
    fetchAndProcessSummary('final summary').catch((error) => {
      console.error('Failed to fetch final summary:', error);
    });
  };

  const handleHypothesesSubmitted = async () => {
    // Refresh the interview data to get the updated evaluation
    await fetchInterview();
    setHypothesesSubmitted(true);
    setOpenEvaluationModal(true);
  };

  const handleRefreshSummary = async () => {
    if (!interviewId || !interview || interview.status === 'completed') return;

    await fetchAndProcessSummary('manual refresh');
  };

  // Map i18n language to speech recognition language code
  const getSpeechLanguage = () => {
    const patientResponseLanguage = interview?.interviewMetadata?.patientResponseLanguage;
    if (patientResponseLanguage === 'es') return 'es-ES';
    if (patientResponseLanguage === 'en') return 'en-US';

    // Legacy interviews follow the interface language.
    const lang = i18n.language;
    if (lang.startsWith('es')) return 'es-ES';
    return 'en-US';
  };

  if (!interviewId) return null;
  if (!interview) return null;

  return (
    <main className="flex gap-8 p-4 min-h-screen bg-gray-100 max-md:flex-col max-sm:p-4 justify-center w-full">
      <PatientProfile
        patient={patient}
        caseTitle={interview?.clinicalCase?.title}
        onRefreshSummary={interview?.status !== 'completed' ? handleRefreshSummary : undefined}
        isLoading={isLoading}
        interviewStatus={interview?.status}
        personality={interview?.personality}
        interviewId={interview.id}
      />
      <section className="flex flex-col flex-1 rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.05)] bg-white max-h-[calc(100vh-150px)]">
        <ChatInterface
          onEndInterview={interview?.status === 'completed' ? undefined : handleEndInterview}
          onShowEvaluation={
            interview?.status === 'completed' ? () => setOpenEvaluationModal(true) : undefined
          }
          durationInSeconds={
            interview?.status === 'completed' ? interview.totalDuration || 0 : undefined
          }
          messages={messages}
          isLoading={isLoading}
          showBottomSpace={interview?.status === 'completed'}
          disabled={isEndInterviewDisabled}
          audioAutoPlayEnabled={audioAutoPlayEnabled}
          onToggleAudioAutoPlay={() => setAudioAutoPlayEnabled((prev) => !prev)}
        />
        {ending && !hypothesesSubmitted ? (
          <ClinicalHypotheses onHypothesesSubmitted={handleHypothesesSubmitted} />
        ) : interview?.status === 'completed' ? null : isOwner ? ( // Show nothing when interview is completed - just the chat history
          <>
            {messageError && (
              <div className="mx-6 mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">
                {messageError}
              </div>
            )}
            <ChatInput
              onSend={handleSendMessage}
              disabled={isLoading}
              language={getSpeechLanguage()}
            />
          </>
        ) : (
          // Show read-only message for non-owners
          <div className="p-4 bg-gray-100 text-center text-gray-600">
            {t('clinicalChat.readOnlyMode')}
          </div>
        )}
      </section>
      <aside className="flex flex-col gap-8 w-80 max-md:w-full">
        {hypothesesSubmitted && submittedHypotheses.length > 0 && (
          <section className="p-8 rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.05)] bg-white">
            <h3 className="mb-4 text-base text-gray-600 font-bold text-left">
              {t('clinicalChat.submittedHypotheses')}
            </h3>
            <div className="space-y-3">
              {submittedHypotheses
                .sort((a, b) => a.hypothesisOrder - b.hypothesisOrder)
                .map((hypothesis) => (
                  <div
                    key={hypothesis.id}
                    className="p-3 max-w-full text-sm text-black rounded-xl bg-gray-50"
                  >
                    <div className="flex items-start gap-2">
                      <span className="text-sm font-medium text-blue-600 bg-blue-100 px-2 py-1 rounded-full">
                        {hypothesis.hypothesisOrder}
                      </span>
                      <p className="text-sm text-gray-700 flex-1 text-left">
                        {hypothesis.hypothesisText}
                      </p>
                    </div>
                  </div>
                ))}
            </div>
          </section>
        )}
        {interview?.status === 'completed' && <TeacherFeedbackSection interviewId={interview.id} />}
        <NotesSection
          title={t('clinicalChat.feedback')}
          placeholder={
            isOwner ? t('clinicalChat.addFeedbackHere') : t('clinicalChat.readOnlyFeedback')
          }
          value={feedback}
          onChange={setFeedback}
          onBlur={handleFeedbackBlur}
          disabled={!isOwner}
          description={t('clinicalChat.feedbackDescription')}
        />
      </aside>
      <Modal size="medium" open={openEndConfirmationModal} closeAction={close} closeOnOutsideClick>
        <EndInterviewConfirmation onCancel={close} onConfirm={confirmEnding} />
      </Modal>

      {evaluationData && (
        <EvaluationResultsModal
          isOpen={openEvaluationModal}
          onClose={() => setOpenEvaluationModal(false)}
          evaluationData={evaluationData}
        />
      )}

      {/* Welcome Modal - shown only on first visit */}
      <WelcomeModal isOpen={openWelcomeModal} onClose={() => setOpenWelcomeModal(false)} />
    </main>
  );
};
