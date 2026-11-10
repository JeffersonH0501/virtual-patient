import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Expand, Pause, Play, Volume2} from 'lucide-react';
import type {InterviewRecap, RecapTurn} from '../../types/recording';
import type {Message} from '../../types/message';
import {resolveRecordingSource} from '../../services/recordings';
import {formatPlaybackTime} from '../../utils/duration';
import {TurnEvidenceDetails} from './TurnEvidenceDetails';
import {Dialog} from '../common/Dialog';
import {useUser} from '../../hooks/useUser';
import {useBlockPlayback} from './useBlockPlayback';

type Props = {recap: InterviewRecap; messages?: Message[]; patientName?: string; patientAvatar?: string; infoDisabled: boolean; seekRequest?: {turnId: string; requestId: number} | null};

export const BlockInterviewRecap = (props: Props) => {
  const {user} = useUser();
  return <BlockInterviewRecapContent key={`${user?.id}:${user?.role}:${user?.organizationId}:${props.recap.interviewId}`} {...props} />;
};

const BlockInterviewRecapContent = ({recap, messages, patientName, patientAvatar, infoDisabled, seekRequest}: Props) => {
  const {t} = useTranslation();
  const {user} = useUser();
  const [detail, setDetail] = useState<RecapTurn | null>(null);
  useEffect(() => {
 if (infoDisabled) setDetail(null);
}, [infoDisabled]);
  const avatar = patientAvatar || messages?.find((item) => item.senderType !== 'user')?.senderAvatar;
  const {togglePlayback, block, nextBlock, time, duration, playing, patientSpeaking, volume, setVolume, error, poster, video, audio, audioSource, patientActive, activeId, seek, videoEvents, audioEvents} = useBlockPlayback(recap, seekRequest);

  return <section className="ui-panel-body min-h-0 flex-1 overflow-x-hidden overflow-y-hidden" aria-label={t('clinicalChat.recap.title')}>
    <div className="recap-content mx-auto flex h-full min-h-0 w-full flex-col gap-layout">
    <div className="shrink-0 overflow-hidden rounded-xl border border-neutral-200 bg-neutral-950">
    <div className="grid grid-cols-2 bg-neutral-900">
      <div className="relative flex aspect-video min-w-0 items-center justify-center overflow-hidden">
        <div className={`relative flex h-20 w-20 items-center justify-center rounded-full ring-4 motion-speaking ${patientSpeaking && patientActive ? 'ring-success-400 shadow-speaking' : 'ring-white/15'}`}>
          {avatar && <img className="h-full w-full rounded-full object-cover" src={avatar} alt="" />}
        </div>
        <div className="absolute inset-x-0 bottom-0 px-inset py-inset text-center text-white secondary-text">{patientName || t('clinicalChat.call.patient')}</div>
      </div>
      <div className="relative aspect-video min-w-0 overflow-hidden">
      {[block, nextBlock].flatMap((item) => item?.studentVideoSource ? [item] : []).map((item) => {
        const active = item.blockId === block?.blockId;
        return <video key={item.blockId} ref={active ? video : undefined} crossOrigin="use-credentials" playsInline preload="auto"
          className={active ? 'aspect-video w-full object-contain' : 'hidden'}
          aria-hidden={!active} src={resolveRecordingSource(item.studentVideoSource) ?? undefined}
          {...videoEvents(active)} />;
      })}
      {!block?.studentVideoSource && <p role="status" className="p-layout text-white">{t('clinicalChat.recap.notAvailable')}</p>}
      {poster && <img src={poster} alt="" className="pointer-events-none absolute inset-0 h-full w-full object-contain" />}
      </div>
    </div>
    <audio key={block?.blockId} ref={audio} crossOrigin="use-credentials" preload="auto" src={audioSource} {...audioEvents} />
    <div className="flex items-center gap-layout bg-neutral-900 px-inset py-inset text-white">
      <button type="button" className="recap-playback-button [&_svg]:h-4 [&_svg]:w-4" disabled={!duration} onClick={togglePlayback} aria-label={playing ? t('clinicalChat.recap.pause') : t('clinicalChat.recap.play')}>{playing ? <Pause /> : <Play />}</button>
      <span className="w-10 text-right tabular-nums secondary-text">{formatPlaybackTime(time)}</span>
      <input type="range" min={0} max={duration} step={.01} value={time} className="min-w-0 flex-1 accent-brand-500" onChange={(event) => seek(Number(event.target.value))} aria-label={t('clinicalChat.recap.timeline')} />
      <span className="w-10 tabular-nums secondary-text">{recap.durationMs == null ? '—' : formatPlaybackTime(duration)}</span>
      <label className="group flex shrink-0 items-center justify-end gap-layout" title={t('clinicalChat.recap.volume')}>
        <span className="block h-4 w-4 [&_svg]:h-full [&_svg]:w-full"><Volume2 aria-hidden="true" /></span>
        <input type="range" min={0} max={1} step={.05} value={volume} className="w-16 min-w-0 cursor-pointer accent-brand-500 sm:w-20" onChange={(event) => setVolume(Number(event.target.value))} aria-label={t('clinicalChat.recap.volume')} />
      </label>
    </div>
    </div>
    {error && <p role="alert">{t('clinicalChat.recap.playbackError')}</p>}
    <div className="recap-transcript-scroll min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto scrollbar-hidden" aria-live="polite">
      <div className="recap-transcript-list flex flex-col gap-layout">
      {recap.turns.map((turn, index) => <div className={`flex items-center justify-end gap-layout ${turn.speaker === 'student' ? 'ml-layout sm:ml-layout' : 'mr-layout flex-row-reverse sm:mr-layout'}`} key={turn.turnId}>
        {user?.role === 'superuser' && <button type="button" className="ui-icon-button ui-icon-button--plain [&_svg]:h-4 [&_svg]:w-4" disabled={infoDisabled} onClick={() => setDetail(turn)} aria-label={t('clinicalChat.recap.turnInfo')} title={t('clinicalChat.recap.turnInfo')}><Expand aria-hidden="true" /></button>}
        <button type="button" className={`recap-turn-bubble ${turn.speaker === 'student' ? 'recap-turn-bubble--student' : ''}`} data-selected={activeId === turn.messageId || undefined} aria-current={activeId === turn.messageId ? 'true' : undefined}
          disabled={turn.startMs == null} onClick={() => seek((turn.startMs ?? 0) / 1000)}>
          <span className="whitespace-pre-wrap text-neutral-800 default-text">{turn.transcript}</span>
          <span className="recap-turn-meta text-neutral-500 secondary-text">{t('clinicalChat.recap.turnNumber', {number: index + 1})}{turn.startMs == null ? '' : `, ${formatPlaybackTime(turn.startMs / 1000)}`}</span>
        </button>
      </div>)}
    </div>
    </div>
    </div>
    <Dialog open={Boolean(detail)} title={t('clinicalChat.recap.turnDetails')} onClose={() => setDetail(null)} size="large">{detail && <TurnEvidenceDetails turn={detail} />}</Dialog>
  </section>;
};
