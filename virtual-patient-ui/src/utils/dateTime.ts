const dateOptions: Intl.DateTimeFormatOptions = {month: 'short', day: 'numeric', year: 'numeric'};
const timeOptions: Intl.DateTimeFormatOptions = {hour: 'numeric', minute: '2-digit', hour12: true};
const dateFormatter = new Intl.DateTimeFormat('en-US', dateOptions);
const timeFormatter = new Intl.DateTimeFormat('en-US', timeOptions);

export const formatDateTimeParts = (value?: string | Date | null) => {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  return {
    date: dateFormatter.format(date),
    time: timeFormatter.format(date).replace(/\s+/g, ' ').toLowerCase(),
  };
};
