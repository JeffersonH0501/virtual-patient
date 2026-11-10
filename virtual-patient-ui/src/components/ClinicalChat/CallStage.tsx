import {useEffect, useRef} from 'react';
import {useTranslation} from 'react-i18next';
import {Camera} from 'lucide-react';

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
      className={`grid grid-cols-1 gap-layout md:flex md:h-full md:min-h-0 md:flex-col md:items-center ${className}`}
      aria-label={t('clinicalChat.call.videoArea')}
    >
      <article className="relative flex aspect-video min-h-0 min-w-0 items-center justify-center overflow-hidden rounded-xl bg-neutral-900 md:h-call-tile md:w-auto md:max-w-full md:flex-none">
        <div
          className={`absolute inset-0 bg-gradient-to-br from-neutral-800 to-neutral-950 motion-opacity ${
            patientSpeaking ? 'opacity-80' : 'opacity-100'
          }`}
        />
        <div
          className={`relative flex h-20 w-20 items-center justify-center rounded-full bg-warning-100 ring-4 motion-speaking sm:h-24 sm:w-24 ${
            patientSpeaking
              ? 'scale-105 ring-success-400 shadow-speaking'
              : 'ring-white/15'
          }`}
        >
          <img
            data-patient-roi-anchor
            src={patientAvatar}
            alt=""
            className="h-patient-avatar w-patient-avatar rounded-full object-cover"
          />
        </div>
        <div className="absolute inset-x-0 bottom-0 bg-black/45 px-inset py-inset text-left text-white backdrop-blur-sm secondary-text">
          <span className="truncate">{patientName || t('clinicalChat.call.patient')}</span>
        </div>
      </article>

      <article className="relative flex aspect-video min-h-0 min-w-0 items-center justify-center overflow-hidden rounded-xl bg-neutral-800 md:h-call-tile md:w-auto md:max-w-full md:flex-none">
        {cameraEnabled && cameraStream ? (
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            className="h-full w-full -scale-x-100 bg-neutral-950 object-contain"
            aria-label={t('clinicalChat.call.studentCamera')}
          />
        ) : (
          <div className="flex max-w-camera-notice flex-col items-center gap-layout px-inset text-center text-neutral-200 secondary-text">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10">
              <span className="block h-camera-icon w-camera-icon [&_svg]:h-full [&_svg]:w-full"><Camera /></span>
            </span>
            <span>{cameraMessage}</span>
            {cameraErrorCode && (
              <button
                type="button"
                onClick={onRetryCamera}
                className="rounded-lg border border-white/30 bg-white/10 px-layout py-layout text-white hover:bg-white/20 secondary-text"
              >
                {t('clinicalChat.call.retryCamera')}
              </button>
            )}
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 bg-black/45 px-inset py-inset text-left text-white backdrop-blur-sm secondary-text">
          <span className="block truncate">{studentName}</span>
        </div>
      </article>
    </section>
  );
};
