import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {AddTeacherFeedbackModal} from './AddTeacherFeedbackModal';

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
  create: vi.fn(),
  close: vi.fn(),
  added: vi.fn(),
}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('../../services/teacherFeedback', () => ({
  updateTeacherFeedback: mocks.update,
  createTeacherFeedback: mocks.create,
}));
const feedback = {
  id: 1,
  medicalInterviewId: 2,
  teacherId: 3,
  feedback: 'Original',
  createdAt: '2026-10-20T12:00:00Z',
};
const openEditor = () =>
  render(
    <AddTeacherFeedbackModal
      isOpen
      onClose={mocks.close}
      interviewId={2}
      onFeedbackAdded={mocks.added}
      editingFeedback={feedback}
    />,
  );
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

it('requires a meaningful edit and disables again after reverting', () => {
  openEditor();
  const save = () =>
    screen.getByRole('button', {name: 'clinicalChat.updateFeedback'}) as HTMLButtonElement;
  expect(save().disabled).toBe(true);
  fireEvent.change(screen.getByRole('textbox'), {target: {value: 'Changed'}});
  expect(save().disabled).toBe(false);
  fireEvent.change(screen.getByRole('textbox'), {target: {value: ' Original '}});
  expect(save().disabled).toBe(true);
});

it('blocks repeated saving and cancellation during an update', async () => {
  let finish: (value: typeof feedback) => void = () => undefined;
  mocks.update.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  openEditor();
  fireEvent.change(screen.getByRole('textbox'), {target: {value: 'Changed'}});
  fireEvent.click(screen.getByRole('button', {name: 'clinicalChat.updateFeedback'}));
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', {name: 'common.cancel'}));
  fireEvent.click(screen.getByRole('button', {name: 'common.loading'}));
  expect(mocks.close).not.toHaveBeenCalled();
  expect(mocks.update).toHaveBeenCalledTimes(1);
  finish({...feedback, feedback: 'Changed'});
  await waitFor(() => expect(mocks.close).toHaveBeenCalledTimes(1));
});
