import {FC} from 'react';

type HypothesesCardProps = {
  hypotheses: string[];
};

export const HypothesesCard: FC<HypothesesCardProps> = ({hypotheses}) => {
  return (
    <section className="p-8 rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.05)] bg-white">
      <h2 className="mb-4 text-lg font-semibold text-gray-800">Clinical Hypotheses</h2>
      {hypotheses.map((hypothesis, index) => (
        <p
          key={index}
          className="p-4 mb-4 text-sm leading-normal text-gray-700 bg-blue-50 rounded-lg"
        >
          {hypothesis}
        </p>
      ))}
    </section>
  );
};
