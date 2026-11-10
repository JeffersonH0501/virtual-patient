import {afterEach, expect, it} from 'vitest';
import {cleanup, render, screen} from '@testing-library/react';
import {DateTime} from './DateTime';
import {formatDateTimeParts} from '../../utils/dateTime';
afterEach(cleanup);
it('renders the shared compact date and local time format', () => {
  const value = new Date(2026, 10, 3, 15, 41);
  const {container} = render(<DateTime value={value} />);
  const time = container.querySelector('time')!;
  expect(time.dateTime).toBe(value.toISOString());
  expect(time.textContent).toBe('Nov 3, 2026 3:41 pm');
});
it('formats midnight and noon with the correct day period', () => {
  expect(formatDateTimeParts(new Date(2026, 8, 23, 0, 5))?.time).toBe('12:05 am');
  expect(formatDateTimeParts(new Date(2026, 8, 23, 12, 5))?.time).toBe('12:05 pm');
});

it('preserves missing dates without inventing a registration time', () => {
  const {rerender, container} = render(<DateTime value={null} fallback="Not available" />);
  expect(screen.getByText('Not available')).toBeDefined();
  expect(container.querySelector('time')).toBeNull();
  rerender(<DateTime value="invalid" />);
  expect(screen.getByText('—')).toBeDefined();
});

