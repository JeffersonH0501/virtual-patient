import {ReactNode} from 'react';

type InterviewLayoutProps = {
  children: ReactNode;
  documentScroll?: boolean;
};

export const ActiveSimulationLayout = ({children}: InterviewLayoutProps) => (
  <section data-interaction-area className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 auto-rows-max gap-layout overflow-y-auto bg-neutral-100 md:grid-cols-simulation-tablet md:grid-rows-1 md:overflow-hidden">
    {children}
  </section>
);

export const SimulationResultsLayout = ({children, documentScroll}: InterviewLayoutProps) => (
  <section className={`grid min-h-0 w-full min-w-0 auto-rows-max gap-layout bg-neutral-100 ${documentScroll ? 'review-layout' : 'grid-cols-1 h-full overflow-y-auto md:grid-cols-2 xl:grid-cols-results-desktop xl:grid-rows-1 xl:overflow-hidden'}`}>
    {children}
  </section>
);
