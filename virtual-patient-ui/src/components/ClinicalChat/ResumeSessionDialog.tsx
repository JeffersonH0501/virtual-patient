import {useTranslation} from 'react-i18next';
import {Dialog} from '../common/Dialog';

type Props = {
  open: boolean;
  forcingTermination: boolean;
  resumingInterview: boolean;
  forceTerminationError: boolean;
  onResume: () => void;
  onForceTermination: () => void;
};

export function ResumeSessionDialog({open, forcingTermination, resumingInterview, forceTerminationError, onResume, onForceTermination}: Props) {
  const {t} = useTranslation();
  const forcedSessionAction = t('clinicalChat.resumeSession.forcedAction');
  const resumeSessionCopy = t('clinicalChat.resumeSession.description').split(forcedSessionAction);
  return (
    <Dialog
      title={t('clinicalChat.resumeSession.title')}
      open={open}
      busy={forcingTermination || resumingInterview}
      hasDismissAction
      actions={
        <>
          <button type="button" className="ui-button ui-button--primary"
            disabled={forcingTermination || resumingInterview} onClick={onResume}>
            {resumingInterview ? t('common.loading') : t('clinicalChat.resumeSession.resume')}
          </button>
          <button type="button" onClick={onForceTermination}
            disabled={forcingTermination || resumingInterview} className="ui-button ui-button--danger">
            {forcingTermination ? t('common.loading') : t('clinicalChat.resumeSession.forceTermination')}
          </button>
        </>
      }
    >
      <p className="text-neutral-600 default-text">
        <span className="whitespace-pre-line">{resumeSessionCopy[0]}{resumeSessionCopy.length > 1 && <><strong>{forcedSessionAction}</strong>{resumeSessionCopy[1]}</>}</span>
      </p>
      {forceTerminationError && (
        <p className="ui-notice ui-notice--danger mt-layout" role="alert">
          {t('clinicalChat.resumeSession.forceError')}
        </p>
      )}
    </Dialog>
  );
}
