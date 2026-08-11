import { FC } from 'react';
import { StudentsTable } from './StudentsTable';
import { StudentsMetricsCards } from './StudentsMetricsCards';

export const Students: FC = () => {

  return (
    <main className="px-4 py-0 mx-auto my-0 w-full pt-20">
      <StudentsMetricsCards />
      <StudentsTable />
    </main>
  );
};
