import {useTranslation} from 'react-i18next';
import {MicrophoneIcon, VolumeIcon} from '../../icons';

type CallToolbarProps = {
  cameraEnabled: boolean;
  elapsedSeconds: number;
  microphoneEnabled: boolean;
  microphoneListening: boolean;
  microphoneSupported: boolean;
  audioEnabled: boolean;
  endDisabled: boolean;
  completed: boolean;
  onToggleCamera: () => void;
  onToggleMicrophone: () => void;
  onToggleAudio: () => void;
  onReportObservation: () => void;
  onEndInterview?: () => void;
  onOpenContext: () => void;
};

export const CallToolbar = ({
  cameraEnabled,
  elapsedSeconds,
  microphoneEnabled,
  microphoneListening,
  microphoneSupported,
  audioEnabled,
  endDisabled,
  completed,
  onToggleCamera,
  onToggleMicrophone,
  onToggleAudio,
  onReportObservation,
  onEndInterview,
  onOpenContext,
}: CallToolbarProps) => {
  const {t} = useTranslation();
  const controlClass =
    'flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border-0 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 sm:h-11 sm:w-11 lg:h-12 lg:w-12';
  const hours = Math.floor(elapsedSeconds / 3600);
  const minutes = Math.floor((elapsedSeconds % 3600) / 60);
  const seconds = elapsedSeconds % 60;
  const elapsedLabel = hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

  return (
    <div className="flex min-w-0 items-center justify-end">
      <div className="flex min-w-0 items-center justify-end gap-2">
        {!completed && (
          <output
            className="min-w-[3.75rem] shrink-0 font-mono text-sm font-semibold tabular-nums text-slate-700 sm:min-w-[4.25rem] sm:text-base"
            aria-label={t('clinicalChat.call.elapsedTime')}
            title={t('clinicalChat.call.elapsedTime')}
          >
            {elapsedLabel}
          </output>
        )}
        {!completed && <button
          type="button"
          onClick={onToggleCamera}
          className={`${controlClass} ${cameraEnabled ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200' : 'bg-rose-100 text-rose-700 hover:bg-rose-200'}`}
          aria-label={cameraEnabled ? t('clinicalChat.call.turnCameraOff') : t('clinicalChat.call.turnCameraOn')}
          title={cameraEnabled ? t('clinicalChat.call.turnCameraOff') : t('clinicalChat.call.turnCameraOn')}
        >
          <svg width="25" height="25" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5h7A2.5 2.5 0 0 1 16 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-7A2.5 2.5 0 0 1 4 16.5v-9Z" stroke="currentColor" strokeWidth="1.8" />
            <path d="m16 10 3.2-2c.8-.5 1.8.1 1.8 1v6c0 .9-1 1.5-1.8 1L16 14v-4Z" stroke="currentColor" strokeWidth="1.8" />
          </svg>
        </button>}
        {!completed && <button
          type="button"
          onClick={onToggleMicrophone}
          disabled={!microphoneSupported || completed}
          className={`${controlClass} ${
            !microphoneSupported || completed
              ? 'cursor-not-allowed bg-slate-100 text-slate-400'
              : microphoneEnabled
                ? `bg-emerald-100 text-emerald-700 hover:bg-emerald-200 ${microphoneListening ? 'ring-2 ring-emerald-300 ring-offset-1' : ''}`
                : 'bg-rose-100 text-rose-700 hover:bg-rose-200'
          }`}
          aria-pressed={microphoneEnabled}
          aria-label={microphoneEnabled ? t('clinicalChat.call.muteMicrophone') : t('clinicalChat.call.enableMicrophone')}
          title={microphoneEnabled ? t('clinicalChat.call.muteMicrophone') : t('clinicalChat.call.enableMicrophone')}
        >
          <span className="scale-125"><MicrophoneIcon color="currentColor" /></span>
        </button>}
        {!completed && <button
          type="button"
          onClick={onToggleAudio}
          className={`${controlClass} ${audioEnabled ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200' : 'bg-rose-100 text-rose-700 hover:bg-rose-200'}`}
          aria-pressed={audioEnabled}
          aria-label={audioEnabled ? t('clinicalChat.disableAudioAutoPlay') : t('clinicalChat.enableAudioAutoPlay')}
          title={audioEnabled ? t('clinicalChat.disableAudioAutoPlay') : t('clinicalChat.enableAudioAutoPlay')}
        >
          <VolumeIcon muted={!audioEnabled} className="h-6 w-6" />
        </button>}
        <button
          type="button"
          onClick={onReportObservation}
          className={`${controlClass} bg-blue-600 text-white hover:bg-blue-700`}
          aria-label={t('clinicalChat.reportObservation')}
          title={t('clinicalChat.reportObservation')}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M6 4h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-7l-4.5 3v-3H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
            <path d="M8 8h8M8 12h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
        <button
          type="button"
          onClick={onOpenContext}
          className={`${controlClass} bg-blue-50 text-blue-700 hover:bg-blue-100 xl:hidden`}
          aria-label={t('clinicalChat.call.openInformation')}
        >
          <span className="text-sm font-semibold">i</span>
        </button>
        {!completed && (
          <button
            type="button"
            onClick={onEndInterview}
            disabled={endDisabled}
            className={`${controlClass} ml-1 bg-red-600 text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-slate-300`}
            aria-label={t('clinicalChat.endInterview')}
            title={t('clinicalChat.endInterview')}
          >
            <svg width="25" height="25" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
              <rect x="8" y="8" width="8" height="8" rx="1.5" fill="currentColor" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
};
