import { FC, ReactNode } from 'react';
import { Button } from '../Button';

interface NonIdealStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export const NonIdealState: FC<NonIdealStateProps> = ({
  title,
  description,
  icon,
  action,
  className = '',
}) => {
  return (
    <div className={`flex flex-col items-center justify-center p-inset text-center ${className}`}>
      {icon && (
        <div className="mb-layout text-neutral-400">
          {icon}
        </div>
      )}

      <h3 className="mb-layout text-neutral-800 default-title">
        {title}
      </h3>

      {description && (
        <p className="mb-layout max-w-md text-neutral-600 ">
          {description}
        </p>
      )}

      {action && (
        <Button
          onClick={action.onClick}
          variant="primary"
        >
          {action.label}
        </Button>
      )}
    </div>
  );
};
