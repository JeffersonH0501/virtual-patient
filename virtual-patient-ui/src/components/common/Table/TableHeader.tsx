type TableHeaderProps = {columns: readonly string[]; hideLastLabel?: boolean};

export const TableHeader = ({columns, hideLastLabel = false}: TableHeaderProps) => (
  <thead><tr>{columns.map((column, index) => (
    <th key={column} scope="col">
      {hideLastLabel && index === columns.length - 1 ? <span className="sr-only">{column}</span> : column}
    </th>
  ))}</tr></thead>
);
