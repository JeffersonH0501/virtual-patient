import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {ConversationTableRow} from './ConversationTableRow';
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {role: 'student'}})}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
afterEach(cleanup);

it('opens an unstarted interview in case calibration with its draft ID', () => {
  const Location = () => {
    const {pathname, state} = useLocation();
    return <output>{pathname} {state?.draftInterviewId}</output>;
  };

  render(<MemoryRouter>
    <Location />
    <table><tbody><ConversationTableRow id="142" status="in_progress"
      createdAt="2026-11-02T12:00:00Z" startTime={null} duration={0}
      clinicalCase={{id: 1, title: 'Synthetic case', description: 'Synthetic', caseType: 'default'}} onDelete={vi.fn()} />
    </tbody></table>
  </MemoryRouter>);

  fireEvent.click(screen.getByRole('row', {name: 'conversations.viewInterview 142'}));
  expect(screen.getByRole('status').textContent).toBe('/interviews/calibration 142');
});
it('shows the persisted numeric interview ID first and groups icon actions in one row', () => {
  render(
    <MemoryRouter>
      <table>
        <tbody>
          <ConversationTableRow
            id="142"
            status="completed"
            createdAt="2026-10-20T12:00:00Z"
            startTime={null}
            duration={60}
            clinicalCase={{
              id: 1,
              title: 'Synthetic case',
              description: 'Synthetic',
              caseType: 'default',
            }}
            onDelete={vi.fn()}
          />
        </tbody>
      </table>
    </MemoryRouter>,
  );
  const cells = screen.getAllByRole('cell');
  expect(cells).toHaveLength(7);
  expect(cells[0].textContent).toBe('142');
  expect(cells[6].querySelector('.ui-table-options--icons')).not.toBeNull();
  expect(screen.getByRole('row', {name: 'conversations.viewInterview 142'})).toBeDefined();
  expect(screen.getByRole('button', {name: 'conversations.deleteInterview'})).toBeDefined();
});

it.each([false, true])('opens an interrupted interview only when technical completion is retryable: %s', (retryable) => {
  render(<MemoryRouter><table><tbody><ConversationTableRow id="142" status="interrupted"
    canRetryCompletion={retryable} createdAt="2026-11-02T12:00:00Z" startTime={null} duration={60}
    clinicalCase={{id: 1, title: 'Synthetic case', description: 'Synthetic', caseType: 'default'}} onDelete={vi.fn()} />
    </tbody></table></MemoryRouter>);
  expect(screen.getByRole('row').getAttribute('tabindex')).toBe(retryable ? '0' : null);
});

it.each([
  ['processing', 'pending', 'conversations.pendingEvaluation'],
  ['processing', 'submitted', 'conversations.evaluating'],
  ['completed', 'pending', 'conversations.pendingEvaluation'],
  ['completed', 'submitted', 'clinicalChat.completed'],
] as const)('labels %s with manual rating %s', (status, manualRatingStatus, label) => {
  render(<MemoryRouter><table><tbody><ConversationTableRow id="142" status={status}
    manualRatingStatus={manualRatingStatus} createdAt="2026-11-02T12:00:00Z" startTime={null} duration={60}
    clinicalCase={{id: 1, title: 'Synthetic case', description: 'Synthetic', caseType: 'default'}} onDelete={vi.fn()} />
  </tbody></table></MemoryRouter>);
  expect(screen.getByText(label)).toBeTruthy();
});

it('navigates with the keyboard and isolates the delete action', () => {
  const onDelete = vi.fn();
  const Location = () => <output data-testid="location">{useLocation().pathname}</output>;
  render(<MemoryRouter><Location /><table><tbody><ConversationTableRow id="142" status="completed"
    createdAt="2026-11-02T12:00:00Z" startTime={null} duration={60}
    clinicalCase={{id: 1, title: 'Synthetic case', description: 'Synthetic', caseType: 'default'}} onDelete={onDelete} />
  </tbody></table></MemoryRouter>);
  const deleteButton = screen.getByRole('button', {name: 'conversations.deleteInterview'});
  fireEvent.keyDown(deleteButton, {key: 'Enter'});
  fireEvent.click(deleteButton);
  expect(onDelete).toHaveBeenCalledExactlyOnceWith(142);
  expect(screen.getByTestId('location').textContent).toBe('/');
  fireEvent.keyDown(screen.getByRole('row'), {key: 'Enter'});
  expect(screen.getByTestId('location').textContent).toBe('/interviews/142/review');
});

it('marks assigned interviews and omits unauthorized deletion', () => {
  render(<MemoryRouter><table><tbody><ConversationTableRow id="142" status="completed" isAssigned
    createdAt="2026-11-02T12:00:00Z" startTime={null} duration={60}
    clinicalCase={{id: 1, title: 'Synthetic case', description: 'Synthetic', caseType: 'default'}} onDelete={vi.fn()} />
  </tbody></table></MemoryRouter>);
  const badges = screen.getByText('conversations.assigned').parentElement!;
  expect(Array.from(badges.children, (badge) => badge.textContent)).toEqual([
    'conversations.assigned', 'conversations.pendingEvaluation',
  ]);
  expect(screen.queryByRole('button', {name: 'conversations.deleteInterview'})).toBeNull();
});
