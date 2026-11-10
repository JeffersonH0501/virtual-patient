import type {FC} from 'react';

type LoadingRowsProps = {
  columns: readonly string[];
  stackedColumns: readonly number[];
  actionCount: number;
};

export const TableLoadingState = ({label}: LoadingRowsProps & {label: string}) => (
  <p className="ui-panel-body" role="status">{label}</p>
);

export const TableLoadingRows: FC<LoadingRowsProps> = () => null;
