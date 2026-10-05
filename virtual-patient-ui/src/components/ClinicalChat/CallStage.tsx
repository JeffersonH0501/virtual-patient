import {useEffect, useRef} from 'react';
import {useTranslation} from 'react-i18next';
import {Camera} from '../../icons';

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
  avatarActive?: boolean;
  avatarConnecting?: boolean;
  avatarError?: string | null;
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
  avatarActive = false,
  avatarConnecting = false,
  avatarError = null,
}: CallStageProps) => {
  const {t} = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = cameraStream;
  }, [cameraStream]);

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
      <article className="relative flex aspect-video min-h-0 min-w-0 items-center justify-center overflow-hidden rounded-xl bg-slate-900 md:h-call-tile md:w-auto md:max-w-full md:flex-none">
        <span data-patient-roi-anchor className="pointer-events-none absolute inset-0" aria-hidden="true" />
        {avatarActive && avatarStream && avatarStream.getVideoTracks().length > 0 ? (
          <video
            ref={(el) => {
              if (el && avatarStream && el.srcObject !== avatarStream) {
                el.srcObject = avatarStream;
              }
            }}
            autoPlay
            playsInline
            muted={true}
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
                  ? 'scale-105 ring-emerald-400 shadow-speaking'
                  : 'ring-white/15'
              }`}
            >
              <img
                src={patientAvatar}
                alt=""
                className="h-patient-avatar w-patient-avatar rounded-full object-cover"
              />
            </div>
          </>
        )}
        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-black/45 px-3 py-2 text-left text-xs text-white backdrop-blur-sm">
          <span className="flex items-center gap-1.5 truncate">
            {patientName || t('clinicalChat.call.patient')}
            {avatarActive && (
              <span className="rounded bg-emerald-500/30 px-1 py-0.5 text-[10px] font-medium text-emerald-200">
                Simli
              </span>
            )}
          </span>
          <span className={patientSpeaking ? 'text-emerald-300' : 'text-slate-300'}>
            {patientSpeaking
              ? t('clinicalChat.call.speaking')
              : t('clinicalChat.call.listening')}
          </span>
        </div>
        {avatarConnecting && (
          <div className="absolute inset-x-3 top-3 rounded bg-black/60 px-2 py-1 text-center text-xs text-white">
            {t('clinicalChat.call.avatarConnecting')}
          </div>
        )}
        {avatarError && (
          <div className="absolute inset-x-3 top-3 rounded border border-amber-500/30 bg-amber-950/80 px-2 py-1 text-center text-xs text-amber-200">
            {t('clinicalChat.call.avatarFallbackNotice')}
          </div>
        )}
      </article>

      <article className="relative flex aspect-video min-h-0 min-w-0 items-center justify-center overflow-hidden rounded-xl bg-slate-800 md:h-call-tile md:w-auto md:max-w-full md:flex-none">
        {cameraEnabled && cameraStream ? (
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            className="h-full w-full -scale-x-100 bg-slate-950 object-contain"
            aria-label={t('clinicalChat.call.studentCamera')}
          />
        ) : (
          <div className="flex max-w-camera-notice flex-col items-center gap-2 px-3 text-center text-xs text-slate-200">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10">
              <span className="block h-camera-icon w-camera-icon [&_svg]:h-full [&_svg]:w-full"><Camera color="currentColor" /></span>
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
