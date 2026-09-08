import {FC, ReactNode} from 'react';

type BadgeProps = {
  variant: 'green' | 'purple' | 'red' | 'blue' | 'orange';
  children: ReactNode;
  className?: string;
};

export const Badge: FC<BadgeProps> = ({variant, children, className = ''}) => {
  return (
    <span className={`ui-badge ui-badge--${variant} ${className}`}>
      {children}
    </span>
  );
};
