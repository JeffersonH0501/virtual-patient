import {ReactNode} from 'react';

type StatCardProps = {
  title: string;
  value: ReactNode;
  icon?: ReactNode;
  change?: string;
  isNegative?: boolean;
};

export const StatCard = ({title, value, icon, change, isNegative}: StatCardProps) => {
  return (
    <article className="flex min-h-36 flex-1 flex-col overflow-hidden rounded-card bg-white shadow-card">
      <header className="flex min-h-12 items-center justify-between border-b border-slate-200 px-4">
        <h2 className="component-title text-left">{title}</h2>
        {icon && <div className="[&_svg]:h-5 [&_svg]:w-5">{icon}</div>}
      </header>
      <div className="flex flex-1 flex-col justify-center px-4 py-3">
        <div className="mb-1 text-3xl font-bold text-slate-800">{value}</div>
        {change && (
          <div className={`text-sm ${isNegative ? 'text-danger-600' : 'text-success-600'}`}>{change}</div>
        )}
      </div>
    </article>
  );
};
