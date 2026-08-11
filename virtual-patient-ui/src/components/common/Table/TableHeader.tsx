import {FC} from 'react';

type TableHeaderProps = {
  columns: readonly string[];
};

export const TableHeader: FC<TableHeaderProps> = ({columns}) => {
  return (
    <thead>
      <tr className="flex px-0 py-3.5 bg-gray-50 border-b border-solid border-t border-gray-200 max-md:min-w-[900px]">
        {columns.map((column, idx) => (
          <th
            key={column}
            className={`${
              idx === 0 ? 'flex-[0.5]' : idx === 1 ? 'flex-[1.5]' : 'flex-1'
            } px-6 py-0 text-xs font-medium tracking-wide text-gray-500 text-left max-sm:px-3 max-sm:py-0`}
          >
            {column}
          </th>
        ))}
      </tr>
    </thead>
  );
};
