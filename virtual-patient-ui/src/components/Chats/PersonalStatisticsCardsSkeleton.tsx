import {FC} from 'react';
import {Skeleton} from '../common';

const SKELETON_STAT_COUNT = 3;

/**
 * Skeleton-loading placeholder for the personal statistics cards. Mirrors the
 * StatCard layout (header + value + change line) while statistics load.
 */
export const PersonalStatisticsCardsSkeleton: FC = () => (
  <div aria-hidden="true" className="grid gap-2 md:grid-cols-3">
    {Array.from({length: SKELETON_STAT_COUNT}).map((_, index) => (
      <article
        key={index}
        className="flex min-h-36 flex-1 flex-col overflow-hidden rounded-card bg-white shadow-card"
      >
        <header className="flex min-h-12 items-center border-b border-slate-200 px-4">
          <Skeleton className="h-4 w-32" />
        </header>
        <div className="flex flex-1 flex-col justify-center px-4 py-3">
          <Skeleton className="mb-2 h-8 w-20" />
          <Skeleton className="h-4 w-28" />
        </div>
      </article>
    ))}
  </div>
);
