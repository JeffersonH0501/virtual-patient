import {FC} from 'react';
import {IconProps} from './types';

export const ComparisonIcon: FC<IconProps> = ({
  color = 'currentColor',
}) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="3" y="4" width="7" height="16" rx="1" />
    <rect x="14" y="4" width="7" height="16" rx="1" />
    <path d="M8 12h8" />
    <path d="M8 8h8" />
    <path d="M8 16h8" />
  </svg>
);
