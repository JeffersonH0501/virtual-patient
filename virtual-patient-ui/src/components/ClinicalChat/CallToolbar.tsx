import {useTranslation} from 'react-i18next';
import {formatPlaybackTime} from '../../utils/duration';

type CallToolbarProps = {
  endDisabled: boolean;
  endDisabledReason?: string;
  onEndInterview?: () => void;
};

export const CallTimer = ({elapsedSeconds}: {elapsedSeconds: number}) => {
  const {t} = useTranslation();
  return (
    <output
      className="shrink-0 font-mono tabular-nums text-neutral-700 numeric-value"
      aria-label={t('clinicalChat.call.elapsedTime')}
      title={t('clinicalChat.call.elapsedTime')}
    >
      {formatPlaybackTime(elapsedSeconds)}
    </output>
  );
};

export const CallToolbar = ({endDisabled, endDisabledReason, onEndInterview}: CallToolbarProps) => {
  const {t} = useTranslation();
  return (
    <footer className="ui-panel-footer flex shrink-0 items-center justify-center">
      <span title={endDisabledReason} tabIndex={endDisabledReason ? 0 : undefined} aria-label={endDisabledReason}>
        <button
          type="button"
          onClick={onEndInterview}
          disabled={endDisabled}
          className="ui-button ui-button--danger call-toolbar-end"
        >
          {t('clinicalChat.endInterview')}
        </button>
      </span>
    </footer>
  );
};
