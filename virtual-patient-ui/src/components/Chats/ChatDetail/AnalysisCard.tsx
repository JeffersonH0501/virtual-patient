import {ProgressBar} from './ProgressBar';

export const AnalysisCard = () => {
  return (
    <section className="p-8 rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.05)] bg-white">
      <h2 className="mb-4 text-lg font-semibold text-gray-800">Conversation Analysis</h2>

      <div className="mb-6">
        <div className="flex justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-600">Empathy Score</h3>
          <span className="text-sm font-semibold text-blue-600">92%</span>
        </div>
        <ProgressBar percentage={92} />
        <p className="mt-2 text-xs text-gray-500 text-left">
          Excellent emotional understanding and patient support demonstrated
        </p>
      </div>

      <div className="mb-6">
        <div className="flex justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-600">Clear Communication</h3>
          <span className="text-sm font-semibold text-blue-600">88%</span>
        </div>
        <ProgressBar percentage={88} />
        <p className="mt-2 text-xs text-gray-500 text-left">
          Questions were clear and well-structured
        </p>
      </div>

      <div className="mb-6">
        <div className="flex justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-600">Professional Conduct</h3>
          <span className="text-sm font-semibold text-blue-600">95%</span>
        </div>
        <ProgressBar percentage={95} />
        <p className="mt-2 text-xs text-gray-500 text-left">
          Maintained high professional standards throughout
        </p>
      </div>
    </section>
  );
};
