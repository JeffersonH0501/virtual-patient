import {FC} from 'react';
import {CaretDown, CaretUp} from '../../../icons';

type ShowMoreProps = {
  onClick: () => void;
  expanded: boolean;
};

export const ShowMore: FC<ShowMoreProps> = ({onClick, expanded}) => {
  return (
    <button
      className="mt-4 flex cursor-pointer items-center gap-1.5 border-none text-sm font-semibold text-blue-600 [&_svg]:h-4 [&_svg]:w-4 [&_svg]:shrink-0"
      onClick={onClick}
    >
      {expanded ? (
        <>
          <span>Show Less</span>
          <CaretUp />
        </>
      ) : (
        <>
          <span>Show More</span>
          <CaretDown />
        </>
      )}{' '}
    </button>
  );
};
