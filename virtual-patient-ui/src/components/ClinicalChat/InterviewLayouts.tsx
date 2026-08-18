import {ReactNode} from 'react';

type InterviewLayoutProps = {
  children: ReactNode;
};

export const ActiveSimulationLayout = ({children}: InterviewLayoutProps) => (
  <main className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 grid-rows-[auto_minmax(0,1fr)] gap-2 overflow-hidden bg-slate-100 md:grid-cols-[clamp(240px,calc(88.8889dvh-115.56px),760px)_minmax(0,1fr)] md:grid-rows-1 xl:grid-cols-[minmax(270px,310px)_clamp(240px,calc(88.8889dvh-115.56px),820px)_minmax(0,1fr)]">
    {children}
  </main>
);

export const SimulationResultsLayout = ({children}: InterviewLayoutProps) => (
  <main className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 gap-2 overflow-hidden bg-slate-100 md:grid-cols-2 xl:grid-cols-[minmax(270px,310px)_minmax(360px,1.1fr)_minmax(340px,0.9fr)]">
    {children}
  </main>
);
