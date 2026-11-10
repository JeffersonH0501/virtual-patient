import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {AssignmentDialog} from './AssignmentDialog';
const request = vi.hoisted(() => vi.fn());
vi.mock('../../services/teacherGrading', () => ({gradingRequest: request}));
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {role: 'superuser'}})}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
const assignments = [
  {id: 11, teacherId: 1, teacherName: 'Teacher 1', status: 'pending'},
  {id: 12, teacherId: 2, teacherName: 'Teacher 2', status: 'in_progress'},
  {id: 13, teacherId: 3, teacherName: 'Teacher 3', status: 'submitted'},
];
const teachers = Array.from({length: 6}, (_, index) => ({
  id: index + 1,
  name: 'Teacher ' + (index + 1),
  email: 'teacher' + (index + 1) + '@example.org',
}));
beforeEach(() => {
  request
    .mockReset()
    .mockImplementation(async (path: string) =>
      path.includes('/users/') ? {users: teachers, total: 6} : assignments,
    );
});
afterEach(cleanup);
it('preselects assignments, locks drafts and submissions and saves the whole selection once', async () => {
  const close = vi.fn();
  const saved = vi.fn();
  render(<AssignmentDialog interviewId={42} onClose={close} onSaved={saved} />);
  const boxes = await screen.findAllByRole('checkbox');
  expect(boxes).toHaveLength(6);
  expect((boxes[0] as HTMLInputElement).checked).toBe(true);
  expect((boxes[1] as HTMLInputElement).disabled).toBe(true);
  expect((boxes[2] as HTMLInputElement).disabled).toBe(true);
  expect(screen.getByText('teacher6@example.org')).toBeDefined();
  expect(screen.queryByRole('navigation')).toBeNull();
  expect((screen.getByRole('button', {name: 'common.save'}) as HTMLButtonElement).disabled).toBe(
    true,
  );
  fireEvent.click(boxes[0]);
  fireEvent.click(boxes[3]);
  let finish: () => void = () => undefined;
  request.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = () => resolve(assignments);
      }),
  );
  fireEvent.click(screen.getByRole('button', {name: 'common.save'}));
  fireEvent.click(screen.getByRole('button', {name: 'common.save'}));
  expect(request.mock.calls.filter((call) => call[1] === 'PUT')).toHaveLength(1);
  expect(request).toHaveBeenLastCalledWith('/medical-interviews/42/teacher-assignments', 'PUT', {
    teacher_ids: [2, 3, 4],
  });
  finish();
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
  expect(close).toHaveBeenCalledTimes(1);
});
it('shows every teacher without search, keeps status on the right and toggles unlocked rows', async () => {
  render(<AssignmentDialog interviewId={42} onClose={vi.fn()} />);
  await screen.findAllByRole('checkbox');
  expect(screen.queryByRole('searchbox')).toBeNull();
  expect(screen.getAllByRole('checkbox')).toHaveLength(6);
  const status = screen.getByText('grading.in_progress').closest('.teacher-assignment-status')!;
  expect(status.children[0].textContent).toBe('grading.in_progress');
  expect(screen.queryByText('grading.assignmentLocked')).toBeNull();
  fireEvent.click(screen.getByText('Teacher 6'));
  expect((screen.getAllByRole('checkbox')[5] as HTMLInputElement).checked).toBe(true);
  fireEvent.click(screen.getByText('teacher6@example.org'));
  expect((screen.getAllByRole('checkbox')[5] as HTMLInputElement).checked).toBe(false);
  fireEvent.click(screen.getByText('Teacher 6'));
  fireEvent.click(screen.getByText('Teacher 2'));
  expect((screen.getAllByRole('checkbox')[1] as HTMLInputElement).checked).toBe(true);
  fireEvent.click(screen.getByRole('button', {name: 'common.save'}));
  await waitFor(() =>
    expect(request).toHaveBeenLastCalledWith('/medical-interviews/42/teacher-assignments', 'PUT', {
      teacher_ids: [1, 2, 3, 6],
    }),
  );
});

it('retains checkbox changes after a failed save and allows retry', async () => {
  render(<AssignmentDialog interviewId={42} onClose={vi.fn()} />);
  const boxes = await screen.findAllByRole('checkbox');
  fireEvent.click(boxes[0]);
  fireEvent.click(boxes[4]);
  request.mockRejectedValueOnce(new Error('Synthetic failure'));
  fireEvent.click(screen.getByRole('button', {name: 'common.save'}));
  await screen.findByRole('alert');
  await waitFor(() =>
    expect((screen.getByRole('button', {name: 'common.save'}) as HTMLButtonElement).disabled).toBe(
      false,
    ),
  );
  expect((screen.getAllByRole('checkbox')[0] as HTMLInputElement).checked).toBe(false);
  expect((screen.getAllByRole('checkbox')[4] as HTMLInputElement).checked).toBe(true);
});
