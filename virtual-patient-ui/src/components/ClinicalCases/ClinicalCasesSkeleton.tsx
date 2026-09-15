import {FC} from 'react';
import {Skeleton} from '../common';

const SKELETON_CARD_COUNT = 5;

/**
 * Skeleton-loading placeholder for the clinical cases page. Mirrors the header
 * and the collapsed case card rows so the layout stays stable while loading.
 */
export const ClinicalCasesSkeleton: FC = () => (
  <section
    aria-hidden="true"
    className="mx-auto w-full max-w-content overflow-x-clip text-left"
  >
    <div className="flex flex-col items-start gap-3 border-b border-slate-200 pb-4 sm:mt-2 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
      <div className="min-w-0">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="mt-2 h-6 w-64" />
      </div>
      <Skeleton className="h-7 w-28 shrink-0 rounded-full" />
    </div>

    <div className="mt-4 w-full min-w-0 self-stretch sm:mt-5">
      <div className="flex min-w-0 flex-col gap-3">
        {Array.from({length: SKELETON_CARD_COUNT}).map((_, index) => (
          <div
            key={index}
            className="flex min-w-0 items-stretch overflow-hidden rounded-case border border-blue-200 bg-blue-50"
          >
            <div className="flex w-11 shrink-0 items-center justify-center border-r border-blue-200 bg-blue-100 px-1 sm:w-14 sm:px-2">
              <Skeleton className="h-4 w-6 bg-blue-200" />
            </div>
            <div className="min-w-0 flex-1 px-3 py-3 sm:px-4">
              <Skeleton className="h-4 w-full max-w-md bg-blue-100" />
            </div>
            <div className="flex w-11 shrink-0 items-center justify-center bg-blue-600 sm:w-14">
              <Skeleton className="h-5 w-5 rounded bg-blue-400" />
            </div>
          </div>
        ))}
      </div>
    </div>
  </section>
);
