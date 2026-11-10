import {forwardRef, InputHTMLAttributes, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Eye, EyeOff} from 'lucide-react';

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  error?: string;
  hint?: string;
};

export const Field = forwardRef<HTMLInputElement, FieldProps>(
  ({id, label, type = 'text', error, hint, className = '', ...props}, ref) => {
    const {t} = useTranslation();
    const [visible, setVisible] = useState(false);
    const description =
      [props['aria-describedby'], hint && id + '-hint', error && id + '-error']
        .filter(Boolean)
        .join(' ') || undefined;
    return (
      <div className={'ui-field ' + className}>
        <label htmlFor={id}>{label}</label>
        <div className={['ui-input-wrapper', (error || props['aria-invalid'] === true || props['aria-invalid'] === 'true') && 'ui-input-wrapper--invalid', type === 'password' && 'ui-input-wrapper--password'].filter(Boolean).join(' ')}>
          <input
            {...props}
            ref={ref}
            id={id}
            inputMode={props.inputMode ?? (type === 'number' ? 'decimal' : undefined)}
            type={type === 'password' && visible ? 'text' : type}
            aria-invalid={error ? true : props['aria-invalid']}
            aria-describedby={description}
          />
          {type === 'password' && (
            <button
              type="button"
              className="ui-password-toggle ui-action-text"
              disabled={props.disabled}
              aria-pressed={visible}
              aria-label={t(visible ? 'auth.hidePassword' : 'auth.showPassword')}
              title={t(visible ? 'auth.hidePassword' : 'auth.showPassword')}
              onClick={() => setVisible((value) => !value)}
            >
              {visible ? <Eye aria-hidden="true" /> : <EyeOff aria-hidden="true" />}
            </button>
          )}
        </div>
        {hint && (
          <p id={id + '-hint'} className="ui-field-hint">
            {hint}
          </p>
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
Field.displayName = 'Field';
