import {InputHTMLAttributes, useState} from 'react';
import {useTranslation} from 'react-i18next';

type AuthFieldProps = InputHTMLAttributes<HTMLInputElement> & {label: string; id: string};

export const AuthField = ({label, id, type = 'text', ...props}: AuthFieldProps) => {
  const [visible, setVisible] = useState(false);
  const {t} = useTranslation();
  const isPassword = type === 'password';

  return (
    <div className="auth-field">
      <label htmlFor={id}>{label}</label>
      <div className="auth-input-wrapper">
        <input {...props} id={id} type={isPassword && visible ? 'text' : type} />
        {isPassword && (
          <button className="auth-password-toggle" type="button"
            aria-label={t(visible ? 'auth.hidePassword' : 'auth.showPassword')}
            aria-pressed={visible} onClick={() => setVisible(!visible)}>
            {t(visible ? 'auth.hide' : 'auth.show')}
          </button>
        )}
      </div>
    </div>
  );
};

