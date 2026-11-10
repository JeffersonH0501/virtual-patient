import {Select, SelectProps} from '../Select';

type CustomSelectProps = Omit<SelectProps, 'options' | 'onValueChange' | 'onChange' | 'label' | 'placeholder' | 'id'> & {
  label: string;
  id: string;
  placeholder: string;
  options: string[];
  onChange: (value: string) => void;
};

export const CustomSelect = ({
  label, id, placeholder, options, onChange, className = '', ...props
}: CustomSelectProps) => (
  <div className={['ui-field', className].filter(Boolean).join(' ')}>
    <label htmlFor={id}>{label}</label>
    <Select
      {...props}
      label={label}
      id={id}
      placeholder={placeholder}
      options={options.map((option) => ({value: option, label: option}))}
      onValueChange={onChange}
    />
  </div>
);
