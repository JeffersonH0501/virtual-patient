import {ReactNode, useId} from 'react';

type Props = {
  actions?: ReactNode;
  pagination?: ReactNode;
  children: ReactNode;
} & ({title: string; titleId?: string} | {title?: never; titleId: string; actions?: never});

export const ListPanel = ({title, titleId, actions, pagination, children}: Props) => {
  const generatedId = useId();
  const headingId = titleId ?? generatedId;
  return (
    <section
      className="ui-panel overflow-hidden"
      aria-labelledby={headingId}
    >
      {title && <header className="ui-panel-header">
        <h2 id={headingId} className="flex-1 text-left default-title">
          {title}
        </h2>
        {actions}
      </header>}
      {pagination}
      <div className="ui-list-content">{children}</div>
    </section>
  );
};
