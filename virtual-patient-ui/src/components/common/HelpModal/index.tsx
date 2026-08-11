import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../Modal';

type HelpModalProps = {
  isOpen: boolean;
  onClose: () => void;
};

export const HelpModal: FC<HelpModalProps> = ({ isOpen, onClose }) => {
  const { t } = useTranslation();

  return (
    <Modal open={isOpen} closeAction={onClose} size="large" containerId="help-modal">
      <div className="flex flex-col h-full max-h-[80vh] rounded-2xl">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-white rounded-t-2xl">
          <h2 className="text-lg font-semibold text-gray-800">
            {t('help.title')}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="space-y-8">
          {/* Purpose Section */}
          <div>
            <h3 className="text-lg font-semibold text-gray-800 mb-3">
              {t('help.purpose.title')}
            </h3>
            <p className="text-gray-600 leading-relaxed">
              {t('help.purpose.description')}
            </p>
          </div>

          {/* Objective Section */}
          <div>
            <h3 className="text-lg font-semibold text-gray-800 mb-3">
              {t('help.objective.title')}
            </h3>
            <p className="text-gray-600 leading-relaxed">
              {t('help.objective.description')}
            </p>
          </div>

          {/* How it Works Section */}
          <div>
            <h3 className="text-lg font-semibold text-gray-800 mb-4">
              {t('help.howItWorks.title')}
            </h3>
            <div className="space-y-3">
              <div className="flex items-start gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-medium">1</span>
                <p className="text-gray-600">{t('help.howItWorks.step1')}</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-medium">2</span>
                <p className="text-gray-600">{t('help.howItWorks.step2')}</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-medium">3</span>
                <p className="text-gray-600">{t('help.howItWorks.step3')}</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-medium">4</span>
                <p className="text-gray-600">{t('help.howItWorks.step4')}</p>
              </div>
            </div>
          </div>

          {/* Clinical Cases Section */}
          <div>
            <h3 className="text-lg font-semibold text-gray-800 mb-3">
              {t('help.clinicalCases.title')}
            </h3>
            <p className="text-gray-600 leading-relaxed mb-3">
              {t('help.clinicalCases.description')}
            </p>
            <ul className="space-y-2 text-gray-600">
              <li className="flex items-start gap-2">
                <span className="text-blue-600 mt-1">•</span>
                <span>{t('help.clinicalCases.feature1')}</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-blue-600 mt-1">•</span>
                <span>{t('help.clinicalCases.feature2')}</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-blue-600 mt-1">•</span>
                <span>{t('help.clinicalCases.feature3')}</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-blue-600 mt-1">•</span>
                <span>{t('help.clinicalCases.feature4')}</span>
              </li>
            </ul>
          </div>

          {/* Additional Information */}
          <div>
            <h3 className="text-lg font-semibold text-gray-800 mb-3">
              {t('help.additionalInfo.title')}
            </h3>
            <p className="text-gray-600 leading-relaxed">
              {t('help.additionalInfo.description')}
            </p>
          </div>
          </div>
        </div>
      </div>
    </Modal>
  );
};
