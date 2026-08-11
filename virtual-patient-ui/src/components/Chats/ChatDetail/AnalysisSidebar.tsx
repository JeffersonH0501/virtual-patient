import {AnalysisCard} from './AnalysisCard';
import {InsightsCard} from './InsightsCard';

export const AnalysisSidebar = () => {
  return (
    <aside className="flex flex-col gap-8 w-80 max-md:w-full">
      <AnalysisCard />
      <InsightsCard />
    </aside>
  );
};
