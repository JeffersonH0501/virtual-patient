import {ReactNode} from 'react';

type InterviewLayoutProps = {
  children: ReactNode;
};

export const ActiveSimulationLayout = ({children}: InterviewLayoutProps) => (
  <main className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 grid-rows-simulation gap-2 overflow-hidden bg-slate-100 md:grid-cols-simulation-tablet md:grid-rows-1 xl:grid-cols-simulation-desktop">
    {children}
  </main>
);

export const SimulationResultsLayout = ({children}: InterviewLayoutProps) => (
  <main className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 gap-2 overflow-hidden bg-slate-100 md:grid-cols-2 xl:grid-cols-results-desktop">
    {children}
  </main>
);
