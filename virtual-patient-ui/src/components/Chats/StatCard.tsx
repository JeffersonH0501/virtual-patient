import {ReactNode} from 'react';

type StatCardProps = {
  title: string;
  value: ReactNode;
  valueTone?: 'info' | 'success' | 'warning';
  icon?: ReactNode;
  change?: string;
  isNegative?: boolean;
};
export const StatCard = ({title, value, valueTone, icon, change, isNegative}: StatCardProps) => {
  const positiveCount = (typeof value === 'number' || typeof value === 'string') && Number(value) > 0;
  return (
    <article className="ui-panel ui-panel--metric motion-enter">
      <div className="flex min-w-0 items-center gap-layout">
        <h2 className="text-left default-title">{title}</h2>
        {icon && <div className="[&_svg]:h-5 [&_svg]:w-5">{icon}</div>}
      </div>
      <div className={`metric-card-value${valueTone && positiveCount ? ' metric-card-value--' + valueTone : ''}`}>{value}</div>
      {change && (
        <div className={`metric-card-note default-text ${isNegative ? 'text-danger-600' : 'text-success-600'}`}>{change}</div>
      )}
    </article>
  );
};

