import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../common/Modal';

type WelcomeModalProps = {
  isOpen: boolean;
  onClose: () => void;
};

export const WelcomeModal: FC<WelcomeModalProps> = ({ isOpen, onClose }) => {
  const { t } = useTranslation();

  return (
    <Modal open={isOpen} closeAction={onClose} size="medium" containerId="welcome-modal">
      <div className="flex flex-col h-full max-h-[80vh] rounded-2xl">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-white rounded-t-2xl">
          <h2 className="text-lg font-semibold text-gray-800">
            {t('clinicalChat.welcome.title')}
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
          <div className="space-y-4">
            <p className="text-gray-700 leading-relaxed">
              {t('clinicalChat.welcome.description1')}
            </p>
            <p className="text-gray-700 leading-relaxed">
              {t('clinicalChat.welcome.description2')}
            </p>
            <p className="text-gray-700 leading-relaxed">
              {t('clinicalChat.welcome.description3')}
            </p>
            <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-800 leading-relaxed">
                {t('clinicalChat.welcome.description4')}
              </p>
            </div>
          </div>
        </div>

      </div>
    </Modal>
  );
};
