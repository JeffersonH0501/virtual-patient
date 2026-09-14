import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {Modal} from '../Modal';
import {X} from '../../../icons';

type HelpModalProps = {
  isOpen: boolean;
  onClose: () => void;
};

const STEP_NUMBERS = [1, 2, 3, 4] as const;
const FEATURE_NUMBERS = [1, 2, 3, 4] as const;

export const HelpModal: FC<HelpModalProps> = ({isOpen, onClose}) => {
  const {t} = useTranslation();

  return (
    <Modal
      open={isOpen}
      closeAction={onClose}
      size="medium"
      containerId="help-modal"
      ariaLabel={t('help.title')}
    >
      <div className="dialog-shell">
        <header className="dialog-header">
          <h2 className="dialog-title">
            {t('help.title')}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="dialog-close-button"
            aria-label={t('common.close')}
            title={t('common.close')}
          >
            <span className="block h-5 w-5 [&_svg]:h-full [&_svg]:w-full">
              <X color="currentColor" />
            </span>
          </button>
        </header>

        <div className="dialog-content flex-1">
          <div className="space-y-6">
            <section>
              <h3 className="component-subtitle">{t('help.purpose.title')}</h3>
              <p className="dialog-copy mt-1.5">{t('help.purpose.description')}</p>
            </section>

            <section>
              <h3 className="component-subtitle">{t('help.objective.title')}</h3>
              <p className="dialog-copy mt-1.5">{t('help.objective.description')}</p>
            </section>

            <section>
              <h3 className="component-subtitle">{t('help.howItWorks.title')}</h3>
              <ol className="mt-3 grid gap-y-2.5">
                {STEP_NUMBERS.map((stepNumber) => (
                  <li key={stepNumber} className="flex items-start gap-2.5">
                    <span className="dialog-copy">{t(`help.howItWorks.step${stepNumber}`)}</span>
                  </li>
                ))}
              </ol>
            </section>

            <section>
              <h3 className="component-subtitle">{t('help.clinicalCases.title')}</h3>
              <p className="dialog-copy mt-1.5">{t('help.clinicalCases.description')}</p>
              <ul className="mt-2.5 grid gap-y-1.5">
                {FEATURE_NUMBERS.map((featureNumber) => (
                  <li key={featureNumber} className="dialog-copy flex items-start gap-2">
                    <span>{t(`help.clinicalCases.feature${featureNumber}`)}</span>
                  </li>
                ))}
              </ul>
            </section>

            <p className="dialog-annotation">
              {t('help.additionalInfo.description')}
            </p>
          </div>
        </div>
      </div>
    </Modal>
  );
};

