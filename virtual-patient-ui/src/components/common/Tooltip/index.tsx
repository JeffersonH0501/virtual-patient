import {FC} from 'react';

type TooltipProps = {
  showTooltip: boolean;
  text: string;
};

export const Tooltip: FC<TooltipProps> = ({showTooltip, text}) => {
  return (
    <>
      {showTooltip && (
        <div className="absolute left-1/2 -translate-x-1/2 bottom-full px-3 py-1 mb-2 text-sm bg-gray-800 text-white rounded whitespace-nowrap">
          {text}
          <div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-800"></div>
        </div>
      )}
    </>
  );
};
