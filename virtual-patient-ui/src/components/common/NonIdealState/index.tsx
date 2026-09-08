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
  className = ''
}) => {
  return (
    <div className={`flex flex-col items-center justify-center min-h-empty-state p-8 text-center ${className}`}>
      {icon && (
        <div className="mb-6 text-gray-400">
          {icon}
        </div>
      )}
      
      <h3 className="mb-4 text-xl font-semibold text-gray-800">
        {title}
      </h3>
      
      {description && (
        <p className="mb-8 max-w-md text-gray-600 leading-relaxed">
          {description}
        </p>
      )}
      
      {action && (
        <Button
          onClick={action.onClick}
          variant="primary"
          size="md"
        >
          {action.label}
        </Button>
      )}
    </div>
  );
};