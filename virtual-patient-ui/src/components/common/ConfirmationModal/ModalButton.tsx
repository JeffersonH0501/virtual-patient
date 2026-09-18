import {FC, ReactNode} from 'react';

type ModalButtonProps = {
  variant: 'primary' | 'secondary' | 'warning';
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
};

export const ModalButton: FC<ModalButtonProps> = ({variant, onClick, children, disabled = false}) => {
  const baseStyles =
    'dialog-action';
  const variantStyles = {
    primary: 'dialog-action--danger',
    secondary: 'dialog-action--secondary',
    warning: 'dialog-action--warning',
  };

  return (
    <button
      className={`${baseStyles} ${variantStyles[variant]}`}
      onClick={onClick}
      type="button"
      disabled={disabled}
    >
      {children}
    </button>
  );
};
