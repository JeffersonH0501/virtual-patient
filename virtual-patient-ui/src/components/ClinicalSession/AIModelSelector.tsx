import {FC} from 'react';
import {CustomSelect} from '../common';

type AIModelSelectorProps = {
  model: string;
  onModelChange: (model: string) => void;
};

export const AIModelSelector: FC<AIModelSelectorProps> = ({model, onModelChange}) => {
  return (
    <CustomSelect
      id="aiModel"
      value={model}
      onChange={onModelChange}
      options={['GPT-4 Clinical', 'GPT-3.5 Clinical']}
      label="AI Model"
      placeholder="Select an AI Model"
    />
  );
};
