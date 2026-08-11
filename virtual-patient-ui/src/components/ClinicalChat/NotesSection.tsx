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
    <section className="p-8 rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.05)] bg-white">
      <h3 className="mb-4 text-base text-gray-600 font-bold text-left">{title}</h3>
      {description && (
        <p className="mb-4 text-sm text-gray-500 text-left">{description}</p>
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
        rows={9}
        resizable={true}
      />
    </section>
  );
};
