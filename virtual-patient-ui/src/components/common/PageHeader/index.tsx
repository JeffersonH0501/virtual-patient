import {ReactNode} from 'react';

type Props = {eyebrow: string; title: string; titleId?: string; children?: ReactNode};

/** Shared page heading, matching the clinical case library at every viewport. */
export const PageHeader = ({eyebrow, title, titleId, children}: Props) => (
  <header className="ui-page-header">
    <div className="min-w-0">
      <p className="tracking-eyebrow compact-text text-brand-600">{eyebrow}</p>
      <h1 id={titleId} className="text-content page-title" data-preserve-case>{title}</h1>
    </div>
    {children}
  </header>
);
