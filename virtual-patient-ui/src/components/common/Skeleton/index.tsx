import {FC} from 'react';

type SkeletonProps = {
  /** Extra classes to size and position the placeholder (width, height, radius, margins). */
  className?: string;
};

/**
 * Base skeleton placeholder. Renders an animated grey block used to build
 * skeleton-loading layouts while real content is being fetched.
 */
export const Skeleton: FC<SkeletonProps> = ({className = ''}) => (
  <div aria-hidden="true" className={`animate-pulse rounded bg-slate-200 ${className}`} />
);
