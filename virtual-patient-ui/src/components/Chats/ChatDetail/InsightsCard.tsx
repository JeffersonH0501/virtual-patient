import {Check, Warning} from '../../../icons';

export const InsightsCard = () => {
  return (
    <section className="p-8 mb-8 rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.05)] bg-white">
      <h2 className="mb-4 text-lg font-semibold text-gray-800">Key Insights</h2>
      <ul className="flex flex-col gap-3">
        <li className="flex gap-2 items-center">
          <Check />
          <span className="text-sm text-gray-700">Thorough symptom exploration</span>
        </li>
        <li className="flex gap-2 items-center">
          <Check />
          <span className="text-sm text-gray-700">Appropriate follow-up questions</span>
        </li>
        <li className="flex gap-2 items-center">
          <Warning />
          <span className="text-sm text-gray-700">Could explore lifestyle factors more</span>
        </li>
      </ul>
    </section>
  );
};
