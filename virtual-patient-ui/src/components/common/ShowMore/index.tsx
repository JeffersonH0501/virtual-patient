import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {ChevronDown} from 'lucide-react';

type ShowMoreProps = {
  onClick: () => void;
  expanded: boolean;
};

export const ShowMore: FC<ShowMoreProps> = ({onClick, expanded}) => {
  const {t} = useTranslation();
  return (
    <button
      className="ui-button ui-button--text mt-layout flex cursor-pointer items-center gap-layout [&_svg]:h-4 [&_svg]:w-4 [&_svg]:shrink-0"
      onClick={onClick}
      aria-expanded={expanded}
    >
      <span>{t(expanded ? 'common.showLess' : 'common.showMore')}</span>
      <ChevronDown className={expanded ? 'motion-chevron rotate-180' : 'motion-chevron'} />
    </button>
  );
};
