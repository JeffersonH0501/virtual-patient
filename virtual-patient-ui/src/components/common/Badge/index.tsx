import {HTMLAttributes} from 'react';

export type BadgeTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone;
};

/** A non-interactive label with shared geometry and a semantic color. */
export const Badge = ({tone = 'neutral', className = '', ...props}: BadgeProps) => (
  <span {...props} className={['ui-badge', `ui-badge--${tone}`, className].filter(Boolean).join(' ')} />
);
