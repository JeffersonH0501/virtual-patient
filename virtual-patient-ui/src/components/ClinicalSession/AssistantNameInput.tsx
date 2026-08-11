import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {FormInput} from '../common';

type AssistantNameInputProps = {
  name: string;
  onNameChange: (name: string) => void;
};

export const AssistantNameInput: FC<AssistantNameInputProps> = ({name, onNameChange}) => {
  const {t} = useTranslation();
  
  return (
    <div className="flex flex-col mt-6">
      <FormInput
        label={t('clinicalSession.assistantName')}
        type="text"
        id="assistantName"
        placeholder={t('clinicalSession.assistantNamePlaceholder')}
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
      />
    </div>
  );
};
