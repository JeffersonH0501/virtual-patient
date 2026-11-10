import {ButtonHTMLAttributes, forwardRef} from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'text' | 'danger';
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({variant = 'primary', className = '', type = 'button', ...props}, ref) => (
    <button
      {...props}
      ref={ref}
      type={type}
      className={['ui-button', 'ui-button--' + variant, className].join(' ')}
    />
  ),
);
Button.displayName = 'Button';
