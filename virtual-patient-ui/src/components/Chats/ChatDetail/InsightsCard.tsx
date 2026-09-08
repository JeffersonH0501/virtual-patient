import {Warning} from '../../../icons';

export const InsightsCard = () => {
  return (
    <section className="p-8 mb-8 rounded-xl shadow-panel-subtle bg-white">
      <h2 className="mb-4 text-lg font-semibold text-gray-800">Key Insights</h2>
      <ul className="flex flex-col gap-3">
        <li className="flex gap-2 items-center">
          <span className="text-sm text-gray-700">Thorough symptom exploration</span>
        </li>
        <li className="flex gap-2 items-center">
          <span className="text-sm text-gray-700">Appropriate follow-up questions</span>
        </li>
        <li className="flex gap-2 items-center">
          <span className="block h-4 w-4 text-warning-500 [&_svg]:h-full [&_svg]:w-full"><Warning /></span>
          <span className="text-sm text-gray-700">Could explore lifestyle factors more</span>
        </li>
      </ul>
    </section>
  );
};
