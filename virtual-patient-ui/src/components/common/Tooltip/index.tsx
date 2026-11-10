import {FC} from 'react';
import {useAppMotion, usePresence} from '../Motion/hooks';

type TooltipProps = {
  showTooltip: boolean;
  text: string;
};

export const Tooltip: FC<TooltipProps> = ({showTooltip, text}) => {
  const {enabled} = useAppMotion();
  const presence = usePresence(showTooltip);
  return (
    <>
      {presence.present && (
        <div role="tooltip" aria-hidden={!showTooltip || undefined} data-ui-motion={enabled ? 'app' : undefined} data-motion-state={presence.state} onAnimationEnd={presence.onAnimationEnd} className="motion-tooltip absolute left-1/2 -translate-x-1/2 bottom-full px-inset py-inset mb-layout bg-neutral-800 text-white rounded whitespace-nowrap default-text">
          {text}
          <div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-neutral-800"></div>
        </div>
      )}
    </>
  );
};
