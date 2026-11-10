import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, within, waitFor} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {Students} from './index';

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  metrics: vi.fn(),
  remove: vi.fn(),
  role: 'superuser',
}));
const translate = (key: string, options?: {from?: number; to?: number; total?: number}) =>
  key === 'pagination.showing'
    ? 'Mostrando ' + options?.from + '-' + options?.to + ' de ' + options?.total + ' entrevistas'
    : key;
vi.mock('react-i18next', () => ({useTranslation: () => ({t: translate})}));
vi.mock('../../hooks/useUser', () => ({
  useUser: () => ({user: {id: 99, role: mocks.role, organizationId: 7}}),
}));
vi.mock('../../services/interviews/getOrganizationInterviews', () => ({
  getOrganizationInterviews: mocks.list,
}));
vi.mock('../../services/teacherGrading', () => ({gradingRequest: vi.fn()}));
vi.mock('../../services/interviews', () => ({deleteInterview: mocks.remove}));
vi.mock('../../services/students/getStudentsMetrics', () => ({getStudentsMetrics: mocks.metrics}));
const interview = {
  id: 42,
  publicId: 'opaque-token',
  userId: 1,
  createdAt: '2026-10-20T14:30:00Z',
  userName: 'Test Student',
  ownerRole: 'student',
  clinicalCaseTitle: 'Case title',
  personality: {name: 'Personality name'},
  status: 'completed',
  totalDuration: 60,
  evaluationScore: null,
  teacherFeedback: [],
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.role = 'superuser';
  mocks.remove.mockReset().mockResolvedValue(undefined);
  mocks.list.mockResolvedValue({interviews: [interview], total: 1});
  mocks.metrics.mockResolvedValue({
    activeCount: 2,
    completedCount: 6,
    averageScore: 4,
    hasData: true,
  });
});
afterEach(cleanup);
const open = () =>
  render(
    <MemoryRouter>
      <Students />
    </MemoryRouter>,
  );

it('shows interview history without statistics or student search', async () => {
  open();
  await screen.findByText(interview.userName);
  expect(mocks.metrics).not.toHaveBeenCalled();
  expect(screen.queryByText('students.activeInterviews')).toBeNull();
  expect(screen.queryByText('students.completedInterviews')).toBeNull();
  expect(screen.queryByRole('searchbox')).toBeNull();
  for (const key of [
    'students.currentlyActive',
    'students.finishedCases',
    'students.evaluations',
  ]) {
    expect(screen.queryByText(key)).toBeNull();
  }
  expect(screen.queryByRole('heading', {name: 'students.history'})).toBeNull();
  expect(screen.getByRole('heading', {name: 'interviewsPage.title'}).classList.contains('text-content')).toBe(true);
  expect(screen.getByText('interviewsPage.eyebrow').classList.contains('text-brand-600')).toBe(true);
  expect(screen.queryByText('students.tableCaption')).toBeNull();
  expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
    'ID',
    'conversations.date',
    'students.participant',
    'conversations.clinicalCase',
    'students.duration',
    'students.status',
    'students.score',
    'conversations.action',
  ]);
  const row = screen.getByText(interview.userName).closest('tr')!;
  const cells = within(row).getAllByRole('cell');
  expect(cells[0].textContent).toBe(String(interview.id));
  expect(cells[1].querySelector('time')?.getAttribute('datetime')).toBe(interview.createdAt);
  expect(cells[2].textContent).toContain(interview.userName);
  expect(cells[2].textContent).toContain('auth.student');
  expect(row.querySelector('.ui-table-options')).not.toBeNull();
  expect(within(row).getAllByRole('button').map((button) => button.getAttribute('aria-label'))).toEqual(['conversations.deleteInterview']);
  expect(screen.queryByRole('button', {name: 'grading.assign'})).toBeNull();
  expect(screen.queryByText('students.reviewByYou')).toBeNull();
  expect(cells[3].textContent).toContain(interview.clinicalCaseTitle);
  expect(cells[3].textContent).toContain(interview.personality.name);
});

it('shows confirmed activity instead of elapsed calendar time for unfinished interviews', async () => {
  mocks.list.mockResolvedValue({interviews: [{...interview, status: 'in_progress',
    startTime: new Date(Date.now() - 18 * 60_000).toISOString(), totalDuration: 60}], total: 1});
  open();
  await screen.findByText('1m');
  expect(screen.queryByText('18m')).toBeNull();
});

it('paginates by ten using the exact total and disables next on the final page', async () => {
  mocks.list
    .mockResolvedValueOnce({
      interviews: [...Array.from({length: 10}, (_, i) => ({...interview, id: i + 1})), {...interview, id: 106}],
      total: 11,
    });
  open();
  await screen.findByText('Mostrando 1-10 de 11 entrevistas');
  expect(mocks.list).toHaveBeenLastCalledWith('7', 0, 100);
  fireEvent.click(screen.getByRole('button', {name: 'common.next'}));
  await screen.findByText('Mostrando 11-11 de 11 entrevistas');
  expect(mocks.list).toHaveBeenCalledTimes(1);
  expect(
    within(screen.getByRole('table')).getAllByRole('row')[1].firstElementChild?.textContent,
  ).toBe('106');
  expect((screen.getByRole('button', {name: 'common.next'}) as HTMLButtonElement).disabled).toBe(
    true,
  );
});

it('shows an exact empty range and recovers from listing errors', async () => {
  mocks.list
    .mockRejectedValueOnce(new Error('errors.generic'))
    .mockResolvedValueOnce({interviews: [], total: 0});
  open();
  await screen.findByRole('alert');
  fireEvent.click(screen.getByRole('button', {name: 'common.retry'}));
  await screen.findByText('students.noInterviews');
  expect(screen.getByText('Mostrando 0-0 de 0 entrevistas')).toBeDefined();
});

it('cancels deletion without a request and refreshes history after confirmation', async () => {
  open();
  fireEvent.click(await screen.findByRole('button', {name: 'conversations.deleteInterview'}));
  fireEvent.click(screen.getByRole('button', {name: 'common.cancel'}));
  expect(mocks.remove).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'conversations.deleteInterview'}));
  mocks.list.mockResolvedValueOnce({interviews: [], total: 0});
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'common.delete'}));
  await screen.findByText('students.noInterviews');
  expect(mocks.remove).toHaveBeenCalledWith(interview.id);
  expect(mocks.metrics).not.toHaveBeenCalled();
  expect(screen.getByText('Mostrando 0-0 de 0 entrevistas')).toBeDefined();
});

it('keeps the dialog open for retry after deletion errors', async () => {
  mocks.remove.mockRejectedValueOnce(new Error('Delete failed'));
  open();
  fireEvent.click(await screen.findByRole('button', {name: 'conversations.deleteInterview'}));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'common.delete'}));
  await screen.findByRole('alert');
  expect(screen.getByText(interview.userName)).toBeDefined();
  mocks.list.mockResolvedValueOnce({interviews: [], total: 0});
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'common.delete'}));
  await screen.findByText('students.noInterviews');
  expect(mocks.remove).toHaveBeenCalledTimes(2);
});

it('blocks duplicate confirmation, cancellation and pagination during deletion', async () => {
  let finish: () => void = () => undefined;
  mocks.remove.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  open();
  fireEvent.click(await screen.findByRole('button', {name: 'conversations.deleteInterview'}));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'common.delete'}));
  expect((screen.getByRole('button', {name: 'common.cancel'}) as HTMLButtonElement).disabled).toBe(
    true,
  );
  fireEvent.click(screen.getByRole('button', {name: 'conversations.deletingInterview'}));
  expect(mocks.remove).toHaveBeenCalledTimes(1);
  expect((screen.getByRole('button', {name: 'common.next'}) as HTMLButtonElement).disabled).toBe(
    true,
  );
  finish();
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});

it('redirects the former teacher listing to the unified interview list', async () => {
  mocks.role = 'teacher';
  const Destination = () => {
    const location = useLocation();
    return <p>{location.pathname + location.search}</p>;
  };
  render(<MemoryRouter><Students /><Destination /></MemoryRouter>);
  await screen.findByText('/interviews');
  expect(screen.queryByRole('button', {name: 'conversations.deleteInterview'})).toBeNull();
  expect(mocks.list).not.toHaveBeenCalled();
});


it.each(['click', 'Enter', ' '])('opens the administrative interview from its row with %s and isolates deletion', async (action) => {
  const Destination = () => <output data-testid="location">{useLocation().pathname}</output>;
  render(<MemoryRouter initialEntries={['/interviews']}><Students /><Destination /></MemoryRouter>);
  const row = await screen.findByRole('row', {name: 'conversations.viewInterview 42'});
  expect(screen.queryByRole('button', {name: 'conversations.viewInterview'})).toBeNull();
  const remove = within(row).getByRole('button', {name: 'conversations.deleteInterview'});
  fireEvent.keyDown(remove, {key: 'Enter'});
  fireEvent.click(remove);
  expect(screen.getByTestId('location').textContent).toBe('/interviews');
  expect(screen.getByRole('dialog')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'common.cancel'}));
  if (action === 'click') fireEvent.click(within(row).getByText(interview.userName));
  else fireEvent.keyDown(row, {key: action});
  expect(screen.getByTestId('location').textContent).toBe('/interviews/42/review');
  expect(mocks.remove).not.toHaveBeenCalled();
});

it('preserves the administrative restriction on opening unfinished interviews', async () => {
  mocks.list.mockResolvedValueOnce({interviews: [{...interview, status: 'in_progress'}], total: 1});
  open();
  const row = (await screen.findByText(interview.userName)).closest('tr')!;
  expect(row.getAttribute('tabindex')).toBeNull();
  expect(row.classList.contains('ui-interactive-row')).toBe(false);
  expect(screen.queryByRole('button', {name: 'conversations.viewInterview'})).toBeNull();
});
