import { FC, ReactNode } from 'react';

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

type ButtonProps = {
  children: ReactNode;
  onClick?: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  className?: string;
  type?: 'button' | 'submit' | 'reset';
};

export const Button: FC<ButtonProps> = ({
  children,
  onClick,
  variant = 'primary',
  size = 'md',
  disabled = false,
  className = '',
  type = 'button',
}) => {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`ui-button ui-button--${variant} ui-button--${size} ${className}`}
    >
      {children}
    </button>
  );
};
