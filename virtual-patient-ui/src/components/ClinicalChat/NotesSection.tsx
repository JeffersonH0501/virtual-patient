import {FC} from 'react';
import {FormInput} from '../common';

type NotesSectionProps = {
  title: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  disabled?: boolean;
  description?: string;
};

export const NotesSection: FC<NotesSectionProps> = ({title, placeholder, value, onChange, onBlur, disabled = false, description}) => {
  return (
    <section className="rounded-xl bg-white p-5 shadow-panel-subtle">
      <h3 className="mb-3 text-left text-base font-bold text-gray-600">{title}</h3>
      {description && (
        <p className="mb-3 text-left text-sm text-gray-500">{description}</p>
      )}
      <FormInput
        label=""
        type="textarea"
        id="notes"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        margin={false}
        disabled={disabled}
        rows={7}
        resizable={false}
      />
    </section>
  );
};
