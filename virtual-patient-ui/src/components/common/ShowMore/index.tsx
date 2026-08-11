import {FC} from 'react';
import {ArrowBottom, ArrowUp} from '../../../icons';

type ShowMoreProps = {
  onClick: () => void;
  expanded: boolean;
};

export const ShowMore: FC<ShowMoreProps> = ({onClick, expanded}) => {
  return (
    <button
      className="flex gap-1.5 items-center mt-4 text-sm font-semibold text-blue-600 cursor-pointer border-none"
      onClick={onClick}
    >
      {expanded ? (
        <>
          <span>Show Less</span>
          <ArrowUp />
        </>
      ) : (
        <>
          <span>Show More</span>
          <ArrowBottom />
        </>
      )}{' '}
    </button>
  );
};
