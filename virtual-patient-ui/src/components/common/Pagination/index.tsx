import {ChevronLeft, ChevronRight} from 'lucide-react';
import {useTranslation} from 'react-i18next';
import {Button} from '../Button';

type Props = {
  page: number;
  onPageChange: (page: number) => void;
  hasNext: boolean;
  disabled?: boolean;
  label: string;
  description?: string;
  totalPages?: number;
};

export const Pagination = ({
  page,
  onPageChange,
  hasNext,
  disabled = false,
  label,
  description,
  totalPages,
}: Props) => {
  const {t} = useTranslation();
  const availablePages = totalPages ?? page + (hasNext ? 1 : 0);
  const count = Math.min(availablePages, 5);
  const first = Math.max(1, Math.min(page - Math.floor(count / 2), availablePages - count + 1));
  const pages = Array.from({length: count}, (_, index) => first + index);
  return (
    <nav className="ui-pagination" aria-label={label}>
      <p>{description ?? t('pagination.page', {page})}</p>
      <div className="ui-button-group flex flex-wrap items-center">
        <Button
          variant="secondary"
          className="ui-icon-button"
          aria-label={t('common.previous')}
          title={t('common.previous')}
          disabled={disabled || page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft />
        </Button>
        {pages.map((number) => (
          <Button
            key={number}
            className="ui-pagination-number"
            variant={number === page ? 'primary' : 'secondary'}
            disabled={disabled}
            aria-current={number === page ? 'page' : undefined}
            aria-label={t('pagination.page', {page: number})}
            onClick={() => onPageChange(number)}
          >
            {number}
          </Button>
        ))}
        <Button
          variant="secondary"
          className="ui-icon-button"
          aria-label={t('common.next')}
          title={t('common.next')}
          disabled={disabled || !hasNext}
          onClick={() => onPageChange(page + 1)}
        >
          <ChevronRight />
        </Button>
      </div>
    </nav>
  );
};
