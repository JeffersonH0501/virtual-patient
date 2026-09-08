import {FC} from 'react';

type TableHeaderProps = {
  columns: readonly string[];
  columnClassNames?: readonly string[];
};

export const TableHeader: FC<TableHeaderProps> = ({columns, columnClassNames}) => {
  return (
    <thead>
      <tr className="flex px-0 py-3.5 bg-gray-50 border-b border-solid border-t border-gray-200 max-md:min-w-table">
        {columns.map((column, idx) => (
          <th
            key={column}
            className={`${columnClassNames?.[idx] || (
              idx === 0 ? 'table-column-compact' : idx === 1 ? 'table-column-expanded' : 'flex-1'
            )
            } min-w-0 px-6 py-0 text-left text-xs font-medium tracking-wide text-gray-500 max-sm:px-3 max-sm:py-0`}
          >
            {column}
          </th>
        ))}
      </tr>
    </thead>
  );
};
