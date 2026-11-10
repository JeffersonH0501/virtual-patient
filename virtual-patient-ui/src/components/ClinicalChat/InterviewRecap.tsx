import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {getInterviewRecap} from '../../services/recordings';
import type {InterviewRecap as InterviewRecapData, RecapTurn} from '../../types/recording';
import type {Message} from '../../types/message';
import {useUser} from '../../hooks/useUser';
import {BlockInterviewRecap} from './BlockInterviewRecap';
import {InterviewContentLoading} from './InterviewContentLoading';

type Props = {
  interviewId: number;
  messages?: Message[];
  patientName?: string;
  patientAvatar?: string;
  infoDisabled?: boolean;
  onRecapLoaded?: (recap: InterviewRecapData) => void;
  seekRequest?: {turnId: string; requestId: number} | null;
  refreshedRecap?: InterviewRecapData | null;
  refreshInProgress?: boolean;
};

const transcriptTurns = (messages: Message[] = []): RecapTurn[] => messages.map((message) => ({
  turnId: `message-${message.id}`, messageId: message.id,
  speaker: message.senderType === 'user' ? 'student' : 'patient', transcript: message.content,
  inputSource: 'message', timingSource: 'unavailable', timingQuality: 'unavailable',
}));

export const InterviewRecap = (props: Props) => {
  const {user} = useUser();
  return <InterviewRecapContent key={`${user?.id}:${user?.role}:${user?.organizationId}:${props.interviewId}`} {...props} />;
};

const InterviewRecapContent = ({interviewId, messages, patientName, patientAvatar, infoDisabled = false, onRecapLoaded,
  seekRequest, refreshedRecap, refreshInProgress = false}: Props) => {
  const {t} = useTranslation();
  const [loadedRecap, setRecap] = useState<InterviewRecapData | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const recap = refreshedRecap?.interviewId === interviewId ? refreshedRecap
    : loadedRecap?.interviewId === interviewId ? loadedRecap : null;
  useEffect(() => {
    if (loadedRecap) onRecapLoaded?.(loadedRecap);
  }, [loadedRecap, onRecapLoaded]);
  useEffect(() => {
    if (refreshInProgress) return;
    let active = true;
    const controller = new AbortController();
    let timer: number | undefined;
    setLoadFailed(false);
    const load = async () => {
      try {
        const next = await getInterviewRecap(interviewId, controller.signal);
        if (!active) return;
        setRecap(next);
        if ([next.observationProcessing?.status, next.evaluationProcessing?.status]
          .some((status) => status === 'queued' || status === 'processing')) {
          timer = window.setTimeout(() => void load(), 3000);
        }
      } catch {
        if (active) setLoadFailed(true);
      }
    };
    void load();
    return () => {
      active = false; controller.abort(); window.clearTimeout(timer);
    };
  }, [interviewId, refreshInProgress, loadAttempt]);

  const display: InterviewRecapData = recap ?? {
    interviewId, recordingStatus: 'unavailable', turns: transcriptTurns(messages),
  };
  return <>
    {loadFailed && <div role="alert" className="text-danger-700 default-text">
      <p>{t('clinicalChat.recap.loadFailed')}</p>
      <button type="button" className="ui-button ui-button--secondary" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>{t('common.retry')}</button>
    </div>}
    {!recap && !loadFailed ? <InterviewContentLoading /> : <BlockInterviewRecap
      recap={display.turns.length ? display : {...display, turns: transcriptTurns(messages)}} messages={messages} patientName={patientName} patientAvatar={patientAvatar}
      infoDisabled={infoDisabled} seekRequest={seekRequest} />}
  </>;
};
