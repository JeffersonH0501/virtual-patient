import {useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Pause, Play, Volume2} from 'lucide-react';
import type {InterviewRecap, RecapTurn} from '../../types/recording';
import type {Message} from '../../types/message';
import {resolveRecordingSource} from '../../services/recordings';
import {formatPlaybackTime} from '../../utils/duration';
import {TurnEvidenceDetails} from './TurnEvidenceDetails';
import {Dialog} from '../common/Dialog';
import {useUser} from '../../hooks/useUser';
import {useTurnPlayback} from './useTurnPlayback';

type Props = {recap: InterviewRecap; messages?: Message[]; patientName?: string; patientAvatar?: string; infoDisabled: boolean; seekRequest?: {turnId: string; requestId: number} | null};

export const TurnInterviewRecap = (props: Props) => {
  const {user} = useUser();
  return <TurnInterviewRecapContent key={`${user?.id}:${user?.role}:${props.recap.interviewId}`} {...props} />;
};

const TurnInterviewRecapContent = ({recap, messages, patientName, patientAvatar, infoDisabled, seekRequest}: Props) => {
  const {t} = useTranslation();
  const {user} = useUser();
  const [detail, setDetail] = useState<RecapTurn | null>(null);
  useEffect(() => {
    if (infoDisabled) setDetail(null);
  }, [infoDisabled]);
  const avatar = patientAvatar || messages?.find((item) => item.senderType !== 'user')?.senderAvatar;
  const {video, videoEvents, togglePlayback, time, duration, playing, volume, setVolume, error, activeId, patientSpeaking, seek} = useTurnPlayback(recap, seekRequest);
  // Bring the requested turn's bubble into view when a jump is requested, so the
  // transcript scrolls to the linked turn (no animation).
  const bubbleRefs = useRef<Record<string, HTMLDivElement | null>>({});
  useEffect(() => {
    if (!seekRequest) return;
    const bubble = bubbleRefs.current[seekRequest.turnId];
    bubble?.scrollIntoView?.({block: 'nearest'});
  }, [seekRequest]);
  const replay = recap.replay;
  const source = replay?.status === 'ready' ? resolveRecordingSource(replay.source) : null;
  const preparing = replay?.status === 'queued' || replay?.status === 'processing';

  return <section className="ui-panel-body min-h-0 flex-1 overflow-x-hidden overflow-y-hidden" aria-label={t('clinicalChat.recap.title')}>
    <div className="recap-content mx-auto flex h-full min-h-0 w-full flex-col gap-layout">
    <div className="shrink-0 overflow-hidden rounded-xl border border-neutral-200 bg-neutral-950">
    {preparing ? <div role="status" className="flex aspect-[32/9] flex-col items-center justify-center gap-layout bg-neutral-900 text-white">
      <div className="calibration-processing-mark" aria-hidden="true"><span /><span /><span /></div>
      <span className="secondary-text">{t('clinicalChat.recap.preparing', {progress: replay?.progress ?? 0})}</span>
    </div> : <>
    <div className="grid grid-cols-2 bg-neutral-900">
      <div className="relative flex aspect-video min-w-0 items-center justify-center overflow-hidden">
        <div className={`relative flex h-20 w-20 items-center justify-center rounded-full ring-4 motion-speaking ${patientSpeaking ? 'scale-105 ring-success-400 shadow-speaking' : 'ring-white/15'}`}>
          {avatar && <img className="h-full w-full rounded-full object-cover" src={avatar} alt="" />}
        </div>
        <div className="absolute inset-x-0 bottom-0 px-inset py-inset text-center text-white secondary-text">{patientName || t('clinicalChat.call.patient')}</div>
      </div>
      <div className="relative aspect-video min-w-0 overflow-hidden">
      {source && <video ref={video} crossOrigin="use-credentials" playsInline preload="auto" src={source}
        className="absolute inset-0 h-full w-full object-contain" {...videoEvents} />}
      {!source && <p role="status" className="absolute inset-0 flex items-center justify-center p-layout text-white">{t('clinicalChat.recap.notAvailable')}</p>}
      </div>
    </div>
    <div className="flex items-center gap-layout bg-neutral-900 px-inset py-inset text-white">
      <button type="button" className="recap-playback-button [&_svg]:h-4 [&_svg]:w-4" disabled={!source} onClick={togglePlayback} aria-label={playing ? t('clinicalChat.recap.pause') : t('clinicalChat.recap.play')}>{playing ? <Pause /> : <Play />}</button>
      <span className="w-10 text-right tabular-nums secondary-text">{formatPlaybackTime(time)}</span>
      <input type="range" min={0} max={duration} step={.01} value={time} disabled={!source} className="min-w-0 flex-1 accent-brand-500" onChange={(event) => seek(Number(event.target.value))} aria-label={t('clinicalChat.recap.timeline')} />
      <span className="w-10 tabular-nums secondary-text">{recap.durationMs == null ? '—' : formatPlaybackTime(duration)}</span>
      <label className="group flex shrink-0 items-center justify-end gap-layout" title={t('clinicalChat.recap.volume')}>
        <span className="block h-4 w-4 [&_svg]:h-full [&_svg]:w-full"><Volume2 aria-hidden="true" /></span>
        <input type="range" min={0} max={1} step={.05} value={volume} className="w-16 min-w-0 cursor-pointer accent-brand-500 sm:w-20" onChange={(event) => setVolume(Number(event.target.value))} aria-label={t('clinicalChat.recap.volume')} />
      </label>
    </div>
    </>}
    </div>
    {error && <p role="alert">{t('clinicalChat.recap.playbackError')}</p>}
    <div className="recap-transcript-scroll min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto scrollbar-hidden" aria-live="polite">
      <div className="recap-transcript-list flex flex-col gap-layout">
      {recap.turns.map((turn, index) => {
        const turnLabel = `${t('clinicalChat.recap.turnNumber', {number: index + 1})}${turn.startMs == null ? '' : `, ${formatPlaybackTime(turn.startMs / 1000)}`}`;
        return <div className={`flex items-center justify-end gap-layout ${turn.speaker === 'student' ? 'ml-layout sm:ml-layout' : 'mr-layout flex-row-reverse sm:mr-layout'}`} key={turn.turnId}>
          <div ref={(element) => {
            bubbleRefs.current[turn.turnId] = element;
          }} className={`recap-turn-bubble recap-turn-bubble--turn ${turn.speaker === 'student' ? 'recap-turn-bubble--student' : ''}`} data-selected={activeId === turn.messageId || undefined}>
            <button type="button" className="recap-transcript-button" disabled={turn.startMs == null || !source} onClick={() => seek((turn.startMs ?? 0) / 1000)} aria-current={activeId === turn.messageId ? 'true' : undefined}>
              <span className="whitespace-pre-wrap text-neutral-800 default-text">{turn.transcript}</span>
            </button>
            {user?.role === 'admin' ? <button type="button" className="ui-action-text recap-turn-meta hover:underline text-neutral-500 secondary-text" disabled={infoDisabled} onClick={() => setDetail(turn)} aria-label={`${t('clinicalChat.recap.turnInfo')}: ${turnLabel}`} title={t('clinicalChat.recap.turnInfo')}>{turnLabel}</button> :
              <span className="recap-turn-meta text-neutral-500 secondary-text">{turnLabel}</span>}
          </div>
        </div>;
      })}
    </div>
    </div>
    </div>
    <Dialog open={Boolean(detail)} title={t('clinicalChat.recap.turnDetails')} onClose={() => setDetail(null)} size="large">{detail && <TurnEvidenceDetails turn={detail} />}</Dialog>
  </section>;
};
