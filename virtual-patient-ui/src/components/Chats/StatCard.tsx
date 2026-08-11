import {ReactNode} from 'react';

type StatCardProps = {
  title: string;
  value: string;
  icon: ReactNode;
  change?: string;
  isNegative?: boolean;
};

export const StatCard = ({title, value, icon, change, isNegative}: StatCardProps) => {
  return (
    <div className="flex-1 p-6 bg-white rounded-lg shadow">
      <div className="flex justify-between items-center mb-4">
        <div className="text-base text-gray-700">{title}</div>
        <div>{icon}</div>
      </div>
      <div className="mb-2 text-3xl font-bold text-gray-900">{value}</div>
      {change && (
        <div className={`text-sm ${isNegative ? 'text-red-500' : 'text-green-500'}`}>{change}</div>
      )}
    </div>
  );
};
