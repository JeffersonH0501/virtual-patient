import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {Pagination} from './index';
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: {page: number}) => (options ? key + ' ' + options.page : key),
  }),
}));
afterEach(cleanup);
it('keeps the last five pages reachable and marks the current page', () => {
  const change = vi.fn();
  render(
    <Pagination page={10} totalPages={10} hasNext={false} onPageChange={change} label="History" />,
  );
  expect(
    screen.getByRole('button', {name: 'pagination.page 10'}).getAttribute('aria-current'),
  ).toBe('page');
  expect((screen.getByRole('button', {name: 'common.next'}) as HTMLButtonElement).disabled).toBe(
    true,
  );
  fireEvent.click(screen.getByRole('button', {name: 'pagination.page 6'}));
  expect(change).toHaveBeenCalledWith(6);
});
it('prevents navigation during loading with an unknown total', () => {
  const change = vi.fn();
  render(<Pagination page={1} hasNext disabled onPageChange={change} label="Users" />);
  fireEvent.click(screen.getByRole('button', {name: 'common.next'}));
  expect(change).not.toHaveBeenCalled();
  expect(
    (screen.getByRole('button', {name: 'common.previous'}) as HTMLButtonElement).disabled,
  ).toBe(true);
});

it('includes the next page when the caller confirms that it exists', () => {
  const change = vi.fn();
  render(<Pagination page={3} hasNext onPageChange={change} label="Users" />);
  expect(screen.getByRole('button', {name: 'pagination.page 3'}).getAttribute('aria-current')).toBe(
    'page',
  );
  expect(screen.getByRole('button', {name: 'pagination.page 4'})).not.toBeNull();
  fireEvent.click(screen.getByRole('button', {name: 'pagination.page 1'}));
  expect(change).toHaveBeenCalledWith(1);
});

it('keeps icon-only previous and next actions accessible and navigable', () => {
  const change = vi.fn();
  render(<Pagination page={2} totalPages={3} hasNext onPageChange={change} label="History" />);
  const previous = screen.getByRole('button', {name: 'common.previous'});
  const next = screen.getByRole('button', {name: 'common.next'});
  expect(previous.textContent).toBe('');
  expect(next.textContent).toBe('');
  expect(previous.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
  expect(next.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
  fireEvent.click(previous);
  fireEvent.click(next);
  expect(change.mock.calls).toEqual([[1], [3]]);
});
