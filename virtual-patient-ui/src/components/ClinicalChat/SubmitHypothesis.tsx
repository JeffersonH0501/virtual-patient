import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {ConfirmationModal} from '../common';

type Props = {
  onCancel: () => void;
  onConfirm: () => void;
  isLoading?: boolean;
};

export const SubmitHypothesis: FC<Props> = ({onCancel, onConfirm, isLoading = false}) => {
  const {t} = useTranslation();
  
  return (
    <ConfirmationModal
      title={t('clinicalChat.submitHypothesis')}
      description={t('clinicalChat.submitHypothesisMessage')}
      onCancel={onCancel}
      onConfirm={onConfirm}
      isLoading={isLoading}
    />
  );
};
