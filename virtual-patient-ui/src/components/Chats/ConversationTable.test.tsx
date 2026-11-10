import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {ConversationTable} from './ConversationTable';
import {getInterviews} from '../../services/interviews/getInterviews';
import {InterviewListItem} from '../../types/interview';
import {LIST_PAGE_SIZE} from '../../utils/pagination';

vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({t: (key: string, options?: {from: number; to: number; total: number}) => key === 'pagination.showing'
    ? `Mostrando ${options?.from}-${options?.to} de ${options?.total} entrevistas` : key}),
}));
vi.mock('../../services/interviews/getInterviews', () => ({getInterviews: vi.fn()}));
vi.mock('./ConversationTableRow', () => ({
  ConversationTableRow: ({id}: {id: string}) => <tr><td>{`Interview ${id}`}</td></tr>,
}));

afterEach(cleanup);

const item = (id: number) => ({id, publicId: String(id), status: 'completed'}) as InterviewListItem;

it('uses the loaded interview summaries when changing pages', async () => {
  const fetchPage = vi.mocked(getInterviews);
  fetchPage.mockResolvedValueOnce(Array.from({length: 11}, (_, index) => item(index + 1)));

  render(<ConversationTable />);
  expect(screen.getByRole('table').querySelectorAll('tbody tr[aria-hidden="true"]')).toHaveLength(LIST_PAGE_SIZE);
  await screen.findByText('Interview 10');
  expect(screen.getByText('Mostrando 1-10 de 11 entrevistas')).toBeTruthy();
  expect(screen.queryByText('Interview 11')).toBeNull();

  fireEvent.click(screen.getByRole('button', {name: 'common.next'}));
  expect(screen.getByText('Interview 11')).toBeDefined();
  expect(screen.getByText('Mostrando 11-11 de 11 entrevistas')).toBeTruthy();
  expect(fetchPage).toHaveBeenCalledExactlyOnceWith(100, 0);
});
