import {AriaAttributes, ChangeEvent, forwardRef, KeyboardEvent, Ref} from 'react';
import {Select} from '../Select';

type Control = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
type FormInputControl = Control | HTMLButtonElement;
type FormInputProps = AriaAttributes & {
  label: string;
  type: string;
  id: string;
  placeholder: string;
  value: string;
  onChange: (event: ChangeEvent<Control>) => void;
  onKeyDown?: (event: KeyboardEvent<FormInputControl>) => void;
  onBlur?: () => void;
  options?: string[];
  disabled?: boolean;
  rows?: number;
  autoFocus?: boolean;
  resizable?: boolean;
  error?: string;
  name?: string;
  required?: boolean;
  autoComplete?: string;
  min?: number | string;
  max?: number | string;
  step?: number | string;
};

export const FormInput = forwardRef<FormInputControl, FormInputProps>(
  (
    {
      label,
      type = 'text',
      id,
      placeholder,
      value,
      onChange,
      onKeyDown,
      onBlur,
      options,
      disabled = false,
      rows = 3,
      autoFocus = false,
      resizable = false,
      error,
      ...props
    },
    ref,
  ) => {
    const common = {
      ...props,
      id,
      value,
      onChange,
      onKeyDown,
      onBlur,
      disabled,
      autoFocus,
      'aria-label': props['aria-label'] || label || placeholder,
      'aria-invalid': error ? true : props['aria-invalid'],
      'aria-describedby':
        [props['aria-describedby'], error && id + '-error'].filter(Boolean).join(' ') || undefined,
    };
    return (
      <div className="ui-field">
        {label && <label htmlFor={id}>{label}</label>}
        {type === 'textarea' ? (
          <textarea
            {...common}
            ref={ref as Ref<HTMLTextAreaElement>}
            placeholder={placeholder}
            rows={rows}
            className={'ui-textarea ' + (resizable ? 'resize-y' : 'resize-none')}
          />
        ) : type === 'select' ? (
          <Select
            ref={ref as Ref<HTMLButtonElement>}
            id={id}
            value={value}
            label={common['aria-label']}
            placeholder={placeholder}
            options={(options ?? []).map((option) => ({value: option, label: option}))}
            onChange={onChange}
            onKeyDown={onKeyDown}
            onBlur={onBlur}
            disabled={disabled}
            autoFocus={autoFocus}
            name={props.name}
            required={props.required}
            autoComplete={props.autoComplete}
            aria-invalid={common['aria-invalid']}
            aria-describedby={common['aria-describedby']}
          />
        ) : (
          <div className={error || props['aria-invalid'] === true || props['aria-invalid'] === 'true' ? 'ui-input-wrapper ui-input-wrapper--invalid' : 'ui-input-wrapper'}>
            <input
              {...common}
              ref={ref as Ref<HTMLInputElement>}
              type={type}
              placeholder={placeholder}
            />
          </div>
        )}
        {error && (
          <p id={id + '-error'} className="ui-field-error" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  },
);
FormInput.displayName = 'FormInput';
