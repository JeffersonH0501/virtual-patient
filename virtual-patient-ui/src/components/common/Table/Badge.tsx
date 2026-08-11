import {FC, ReactNode} from 'react';

type BadgeProps = {
  variant: 'green' | 'purple' | 'red' | 'blue' | 'orange';
  children: ReactNode;
  className?: string;
};

const variantStyles = {
  green: 'text-emerald-800 bg-emerald-100',
  purple: 'text-violet-800 bg-violet-100',
  red: 'text-red-800 bg-red-100',
  blue: 'text-blue-800 bg-blue-100',
  orange: 'text-orange-800 bg-orange-100',
};

export const Badge: FC<BadgeProps> = ({variant, children, className = ''}) => {
  return (
    <span className={`px-2 py-1 text-xs font-semibold rounded-full ${variantStyles[variant]} ${className}`}>
      {children}
    </span>
  );
};
