import {useTranslation} from 'react-i18next';
import {Info, Siren, Stop} from '../../icons';

type CallToolbarProps = {
  elapsedSeconds: number;
  controlsDisabled?: boolean;
  endDisabled: boolean;
  completed: boolean;
  onReportObservation: () => void;
  onEndInterview?: () => void;
  onOpenContext: () => void;
};

export const CallToolbar = ({
  elapsedSeconds,
  controlsDisabled = false,
  endDisabled,
  completed,
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
            className="min-w-call-timer shrink-0 font-mono text-sm font-semibold tabular-nums text-slate-700 sm:min-w-call-timer-wide sm:text-base"
            aria-label={t('clinicalChat.call.elapsedTime')}
            title={t('clinicalChat.call.elapsedTime')}
          >
            {elapsedLabel}
          </output>
        )}
        <button
          type="button"
          onClick={onReportObservation}
          disabled={controlsDisabled}
          className={`${controlClass} ${controlsDisabled ? 'cursor-not-allowed bg-slate-100 text-slate-400' : 'bg-warning-100 text-warning-800 hover:bg-warning-200'}`}
          aria-label={t('clinicalChat.reportObservation')}
          title={t('clinicalChat.reportObservation')}
        >
          <span className="block h-6 w-6 [&_svg]:h-full [&_svg]:w-full"><Siren color="currentColor" /></span>
        </button>
        <button
          type="button"
          onClick={onOpenContext}
          className={`${controlClass} bg-blue-50 text-blue-700 hover:bg-blue-100 xl:hidden`}
          aria-label={t('clinicalChat.call.openInformation')}
        >
          <span className="block h-5 w-5 [&_svg]:h-full [&_svg]:w-full"><Info color="currentColor" /></span>
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
            <span className="block h-stop-icon w-stop-icon [&_svg]:h-full [&_svg]:w-full"><Stop color="currentColor" /></span>
          </button>
        )}
      </div>
    </div>
  );
};
