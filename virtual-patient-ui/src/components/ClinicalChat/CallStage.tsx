import {useEffect, useRef} from 'react';
import {useTranslation} from 'react-i18next';
import patientImageM from '../../assets/patient_m.png';

type CallStageProps = {
  className?: string;
  patientAvatar: string;
  patientName: string;
  studentName: string;
  patientSpeaking: boolean;
  cameraStream: MediaStream | null;
  cameraEnabled: boolean;
  cameraStarting: boolean;
  cameraErrorCode: string | null;
  onRetryCamera: () => void;
  avatarStream?: MediaStream | null;
  avatarPilotActive?: boolean;
  avatarPilotConnecting?: boolean;
  avatarPilotError?: string | null;
};

export const CallStage = ({
  className = '',
  patientAvatar,
  patientName,
  studentName,
  patientSpeaking,
  cameraStream,
  cameraEnabled,
  cameraStarting,
  cameraErrorCode,
  onRetryCamera,
  avatarStream = null,
  avatarPilotActive = false,
  avatarPilotConnecting = false,
  avatarPilotError = null,
}: CallStageProps) => {
  const {t} = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const patientVideoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = cameraStream;
  }, [cameraStream]);

  useEffect(() => {
    if (patientVideoRef.current) patientVideoRef.current.srcObject = avatarStream;
  }, [avatarStream]);

  const cameraMessage = cameraStarting
    ? t('clinicalChat.call.cameraStarting')
    : cameraErrorCode
      ? t(`clinicalChat.call.cameraErrors.${cameraErrorCode}`)
      : t('clinicalChat.call.cameraOff');

  return (
    <section
      className={`grid grid-cols-1 gap-2 md:flex md:h-full md:min-h-0 md:flex-col md:items-center ${className}`}
      aria-label={t('clinicalChat.call.videoArea')}
    >
      <article className="relative flex aspect-video min-h-0 min-w-0 items-center justify-center overflow-hidden rounded-xl bg-slate-900 md:h-[calc((100%_-_0.5rem)/2)] md:w-auto md:max-w-full md:flex-none">
        {avatarPilotActive && avatarStream && avatarStream.getVideoTracks().length > 0 ? (
          <video
            ref={(el) => {
              if (el && avatarStream && el.srcObject !== avatarStream) {
                el.srcObject = avatarStream;
              }
            }}
            autoPlay
            playsInline
            muted={false}
            className="h-full w-full object-cover"
            aria-label={patientName || t('clinicalChat.call.patient')}
          />
        ) : (
          <>
            <div
              className={`absolute inset-0 bg-gradient-to-br from-slate-800 to-slate-950 transition-opacity ${
                patientSpeaking ? 'opacity-80' : 'opacity-100'
              }`}
            />
            <div
              className={`relative flex h-20 w-20 items-center justify-center rounded-full bg-amber-100 ring-4 transition-all sm:h-24 sm:w-24 ${
                patientSpeaking
                  ? 'scale-105 ring-emerald-400 shadow-[0_0_30px_rgba(52,211,153,0.35)]'
                  : 'ring-white/15'
              }`}
            >
              <img
                src={patientAvatar || patientImageM}
                alt={patientName || 'Patient'}
                onError={(e) => {
                  e.currentTarget.onerror = null;
                  e.currentTarget.src = patientImageM;
                }}
                className="h-[86%] w-[86%] rounded-full object-cover"
              />
            </div>
          </>
        )}
        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 bg-black/45 px-3 py-2 text-left text-xs text-white backdrop-blur-sm">
          <span className="flex items-center gap-1.5 truncate">
            {patientName || t('clinicalChat.call.patient')}
            {avatarPilotActive && (
              <span className="rounded bg-sky-500/30 px-1 py-0.5 text-[10px] font-medium text-sky-200">
                Pilot
              </span>
            )}
          </span>
          <span className={patientSpeaking ? 'text-emerald-300' : 'text-slate-300'}>
            {patientSpeaking
              ? t('clinicalChat.call.speaking')
              : t('clinicalChat.call.listening')}
          </span>
        </div>
        {(avatarPilotConnecting || avatarPilotError) && (
          <div className="absolute inset-x-3 top-3 rounded bg-black/60 px-2 py-1 text-xs text-white">
            {avatarPilotError || 'Connecting Azure Avatar...'}
          </div>
        )}
      </article>

      <article className="relative flex aspect-video min-h-0 min-w-0 items-center justify-center overflow-hidden rounded-xl bg-slate-800 md:h-[calc((100%_-_0.5rem)/2)] md:w-auto md:max-w-full md:flex-none">
        {cameraEnabled && cameraStream ? (
          <video
            ref={(el) => {
              if (el && cameraStream && el.srcObject !== cameraStream) {
                el.srcObject = cameraStream;
              }
            }}
            autoPlay
            muted
            playsInline
            className="h-full w-full scale-x-[-1] bg-slate-950 object-contain"
            aria-label={t('clinicalChat.call.studentCamera')}
          />
        ) : (
          <div className="flex max-w-[210px] flex-col items-center gap-2 px-3 text-center text-xs text-slate-200">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5h7A2.5 2.5 0 0 1 16 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-7A2.5 2.5 0 0 1 4 16.5v-9Z" stroke="currentColor" strokeWidth="1.8" />
                <path d="m16 10 3.2-2c.8-.5 1.8.1 1.8 1v6c0 .9-1 1.5-1.8 1L16 14v-4Z" stroke="currentColor" strokeWidth="1.8" />
              </svg>
            </span>
            <span>{cameraMessage}</span>
            {cameraErrorCode && (
              <button
                type="button"
                onClick={onRetryCamera}
                className="rounded-lg border border-white/30 bg-white/10 px-2 py-1 text-xs text-white hover:bg-white/20"
              >
                {t('clinicalChat.call.retryCamera')}
              </button>
            )}
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 bg-black/45 px-3 py-2 text-left text-xs text-white backdrop-blur-sm">
          <span className="block truncate">{studentName}</span>
        </div>
      </article>
    </section>
  );
};
