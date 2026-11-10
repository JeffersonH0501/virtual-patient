type Props = {title: string; personality?: string | null};

export const ClinicalCaseCell = ({title, personality}: Props) => (
  <div className="ui-text-pair">
    <span className="text-content default-text">{title}</span>
    <span className="text-content-muted secondary-text">{personality || 'N/A'}</span>
  </div>
);
