import {Dialog} from '../Dialog';
import {FC} from 'react';
import {useTranslation} from 'react-i18next';

type HelpModalProps = {
  isOpen: boolean;
  onClose: () => void;
};

const STEP_NUMBERS = [1, 2, 3, 4] as const;
const FEATURE_NUMBERS = [1, 2, 3, 4] as const;

export const HelpModal: FC<HelpModalProps> = ({isOpen, onClose}) => {
  const {t} = useTranslation();

  return (
    <Dialog
      title={t('help.title')}
      open={isOpen}
      onClose={onClose}
      size="large"
      containerId="help-modal"
    >
      <section className="dialog-reading-section">
        <h3>{t('help.purpose.title')}</h3>
        <p className="dialog-copy">{t('help.purpose.description')}</p>
      </section>

      <section className="dialog-reading-section">
        <h3>{t('help.objective.title')}</h3>
        <p className="dialog-copy">{t('help.objective.description')}</p>
      </section>

      <section className="dialog-reading-section">
        <h3>{t('help.howItWorks.title')}</h3>
        <ol className="dialog-list">
          {STEP_NUMBERS.map((stepNumber) => (
            <li key={stepNumber}>{t(`help.howItWorks.step${stepNumber}`)}</li>
          ))}
        </ol>
      </section>

      <section className="dialog-reading-section">
        <h3>{t('help.clinicalCases.title')}</h3>
        <p className="dialog-copy">{t('help.clinicalCases.description')}</p>
        <ul className="dialog-list">
          {FEATURE_NUMBERS.map((featureNumber) => (
            <li key={featureNumber}>{t(`help.clinicalCases.feature${featureNumber}`)}</li>
          ))}
        </ul>
      </section>

      <p className="dialog-annotation">{t('help.additionalInfo.description')}</p>
    </Dialog>
  );
};
