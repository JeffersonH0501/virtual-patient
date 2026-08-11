import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {ConfirmationModal} from '../common';

type Props = {
  onCancel: () => void;
  onConfirm: () => void;
};

export const EndInterviewConfirmation: FC<Props> = ({onCancel, onConfirm}) => {
  const {t} = useTranslation();
  
  return (
    <ConfirmationModal
      title={t('clinicalChat.endInterview')}
      description={t('clinicalChat.confirmEndInterviewMessage')}
      onCancel={onCancel}
      onConfirm={onConfirm}
    />
  );
};
