import {useState} from 'react';
import {ShowMore} from '../../common';

export const NotesCard = () => {
  const [expanded, setExpanded] = useState(false);

  const toggleExpanded = () => {
    setExpanded(!expanded);
  };

  return (
    <section className="p-8 rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.05)] bg-white">
      <h2 className="mb-4 text-lg font-semibold text-gray-800">Doctor's Notes</h2>
      <div
        className={`px-4 py-5 bg-gray-50 rounded-lg ${expanded ? 'max-h-none' : 'max-h-52 overflow-hidden'}`}
      >
        <p className="text-sm leading-normal text-gray-700">
          Patient presents with recurring morning headaches. Symptoms suggest possible tension
          headaches. Need to monitor sleep patterns and stress levels. Consider lifestyle changes
          such as regular exercise, proper hydration, and a balanced diet. Additionally, recommend
          reducing screen time before bed and practicing relaxation techniques. Follow up in two
          weeks to assess progress and make any necessary adjustments to the treatment plan.
        </p>
      </div>
      <ShowMore onClick={toggleExpanded} expanded={expanded} />
    </section>
  );
};
