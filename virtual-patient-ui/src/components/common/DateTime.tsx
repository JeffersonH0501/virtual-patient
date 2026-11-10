import {formatDateTimeParts} from '../../utils/dateTime';

type DateTimeProps = {value?: string | Date | null; fallback?: string};

export const DateTime = ({value, fallback = '—'}: DateTimeProps) => {
  const formatted = formatDateTimeParts(value);
  if (!formatted || !value) return <span>{fallback}</span>;
  return (
    <time dateTime={typeof value === 'string' ? value : value.toISOString()} className="ui-date-time">
      <span>{formatted.date}</span>{' '}<span>{formatted.time}</span>
    </time>
  );
};
