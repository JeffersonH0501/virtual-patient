import {FC} from 'react';

type StatusIndicatorProps = {
  online?: boolean;
  status?: 'online' | 'completed' | 'offline';
};

export const StatusIndicator: FC<StatusIndicatorProps> = ({online, status}) => {
  // For backward compatibility, if online is provided, use it
  if (online !== undefined) {
    return online ? (
      <span className="absolute bottom-0 right-0 w-5 h-5 bg-success-400 rounded-full border-2 border-solid border-white right-status-dot" />
    ) : null;
  }

  // New status-based approach
  if (!status) return null;

  const getStatusColor = () => {
    switch (status) {
      case 'online':
        return 'bg-success-400';
      case 'completed':
        return 'bg-danger-400';
      case 'offline':
        return 'bg-neutral-400';
      default:
        return 'bg-neutral-400';
    }
  };

  return (
    <span className={`absolute bottom-0 right-0 w-5 h-5 ${getStatusColor()} rounded-full border-2 border-solid border-white right-status-dot`} />
  );
};
