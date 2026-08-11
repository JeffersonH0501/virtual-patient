import {FC} from 'react';

type StatusIndicatorProps = {
  online?: boolean;
  status?: 'online' | 'completed' | 'offline';
};

export const StatusIndicator: FC<StatusIndicatorProps> = ({online, status}) => {
  // For backward compatibility, if online is provided, use it
  if (online !== undefined) {
    return online ? (
      <span className="absolute bottom-0 right-0 w-5 h-5 bg-green-400 rounded-full border-2 border-solid border-white right-[12px]" />
    ) : null;
  }

  // New status-based approach
  if (!status) return null;

  const getStatusColor = () => {
    switch (status) {
      case 'online':
        return 'bg-green-400';
      case 'completed':
        return 'bg-red-400';
      case 'offline':
        return 'bg-gray-400';
      default:
        return 'bg-gray-400';
    }
  };

  return (
    <span className={`absolute bottom-0 right-0 w-5 h-5 ${getStatusColor()} rounded-full border-2 border-solid border-white right-[12px]`} />
  );
};
