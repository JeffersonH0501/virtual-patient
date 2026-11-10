import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {ClinicalHypotheses} from './ClinicalHypotheses';

const api = vi.hoisted(() => ({create: vi.fn(), complete: vi.fn()}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('react-router-dom', () => ({useParams: () => ({interviewId: '7'})}));
vi.mock('../../services/hypotheses', () => ({createHypothesis: api.create}));
vi.mock('../../services/interviews', () => ({completeInterview: api.complete}));
beforeEach(() => {
  vi.resetAllMocks();
  api.create.mockResolvedValue([]);
  api.complete.mockResolvedValue({});
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const enter = () =>
  fireEvent.change(screen.getByPlaceholderText('clinicalChat.enterHypothesis1'), {
    target: {value: 'Synthetic hypothesis'},
  });

it('submits demo hypotheses locally without saving or completing an interview', () => {
  const onDemoSubmit = vi.fn();
  render(<ClinicalHypotheses onCancel={vi.fn()} onDemoSubmit={onDemoSubmit} />);
  fireEvent.click(screen.getByText('clinicalChat.submit'));
  expect(onDemoSubmit).not.toHaveBeenCalled();
  enter();
  fireEvent.click(screen.getByText('clinicalChat.submit'));
  expect(onDemoSubmit).toHaveBeenCalledOnce();
  expect(api.create).not.toHaveBeenCalled();
  expect(api.complete).not.toHaveBeenCalled();
});

it('allows cancel before stopping capture', () => {
  const onCancel = vi.fn();
  render(<ClinicalHypotheses canCancel onCancel={onCancel} onCompleted={vi.fn()} />);
  fireEvent.click(screen.getByText('common.cancel'));
  expect(onCancel).toHaveBeenCalledOnce();
});

it('keeps hypotheses editable and cancellation available during media preservation', () => {
  const cancel = vi.fn();
  render(<ClinicalHypotheses preparingCapture onCancel={cancel} onCompleted={vi.fn()} />);
  enter();
  expect((screen.getByPlaceholderText('clinicalChat.enterHypothesis1') as HTMLTextAreaElement).disabled).toBe(false);
  expect(screen.queryByText('clinicalChat.finalization.savingDescription')).toBeNull();
  fireEvent.click(screen.getByText('common.cancel'));
  expect(cancel).toHaveBeenCalledOnce();
  expect(screen.queryByText('clinicalChat.resumeSession.forceTermination')).toBeNull();
  expect(api.create).not.toHaveBeenCalled();
});

it('blocks form submission and interruption while capture is being preserved', () => {
  const interrupt = vi.fn();
  render(<ClinicalHypotheses onCancel={vi.fn()} onCompleted={vi.fn()} preparingCapture onInterrupt={interrupt} canCancel={false} />);
  enter();
  fireEvent.submit(screen.getByPlaceholderText('clinicalChat.enterHypothesis1').closest('form')!);
  expect(screen.queryByText('clinicalChat.resumeSession.forceTermination')).toBeNull();
  expect(api.create).not.toHaveBeenCalled();
  expect(interrupt).not.toHaveBeenCalled();
});

it('does not permit cancel or editing after capture has stopped, including an error', async () => {
  const onCancel = vi.fn();
  const {rerender} = render(
    <ClinicalHypotheses
      canCancel
      onCancel={onCancel}
      beforeComplete={async () => false}
      onCompleted={vi.fn()}
    />,
  );
  enter();
  fireEvent.click(screen.getByText('clinicalChat.submit'));
  await screen.findByText('common.retry');
  rerender(
    <ClinicalHypotheses
      canCancel={false}
      onCancel={onCancel}
      beforeComplete={async () => false}
      onCompleted={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByText('common.cancel'));
  expect(onCancel).not.toHaveBeenCalled();
  expect(
    (screen.getByPlaceholderText('clinicalChat.enterHypothesis1') as HTMLTextAreaElement).disabled,
  ).toBe(true);
  expect(api.complete).not.toHaveBeenCalled();
});

it('retries recording finalization without posting the saved hypotheses again', async () => {
  const beforeComplete = vi.fn().mockResolvedValueOnce(false).mockResolvedValue(true);
  render(
    <ClinicalHypotheses onCancel={vi.fn()} beforeComplete={beforeComplete} onCompleted={vi.fn()} />,
  );
  enter();
  fireEvent.click(screen.getByText('clinicalChat.submit'));
  fireEvent.click(await screen.findByText('common.retry'));
  await waitFor(() => expect(api.complete).toHaveBeenCalledOnce());
  expect(api.create).toHaveBeenCalledOnce();
});

it('binds saved hypotheses and completion to the sealed capture segment', async () => {
  render(<ClinicalHypotheses captureSegmentId="sealed-segment" onCancel={vi.fn()} onCompleted={vi.fn()} beforeComplete={async () => true} />);
  enter();
  fireEvent.click(screen.getByText('clinicalChat.submit'));
  await waitFor(() => expect(api.complete).toHaveBeenCalledWith('7', 'user_completed', 'sealed-segment'));
  expect(api.create).toHaveBeenCalledWith('7', expect.any(Array), 'sealed-segment');
});

it('accepts only one submission when two submit events arrive before a render', async () => {
  api.create.mockReturnValue(new Promise(() => undefined));
  render(<ClinicalHypotheses onCancel={vi.fn()} onCompleted={vi.fn()} />);
  enter();
  const form = screen.getByPlaceholderText('clinicalChat.enterHypothesis1').closest('form')!;
  act(() => {
    fireEvent.submit(form);
    fireEvent.submit(form);
  });
  expect(api.create).toHaveBeenCalledOnce();
});

it('shows the concrete recording failure inside the terminal retry dialog', async () => {
  render(
    <ClinicalHypotheses
      onCancel={vi.fn()}
      beforeComplete={async () => false}
      onCompleted={vi.fn()}
      recordingError="Synthetic turn persistence failed"
    />,
  );
  enter();
  fireEvent.click(screen.getByText('clinicalChat.submit'));
  await screen.findByText('common.retry');
  expect(screen.queryByText('Synthetic turn persistence failed')).not.toBeNull();
});

it('keeps a failed completion terminal after media was saved and retries without duplicating hypotheses', async () => {
  api.complete
    .mockRejectedValueOnce(new Error('Synthetic completion failure'))
    .mockResolvedValue({});
  const onCancel = vi.fn();
  const beforeComplete = vi.fn().mockResolvedValue(true);
  const {rerender} = render(
    <ClinicalHypotheses
      onCancel={onCancel}
      beforeComplete={beforeComplete}
      onCompleted={vi.fn()}
    />,
  );
  enter();
  fireEvent.click(screen.getByText('clinicalChat.submit'));
  await screen.findByText('common.retry');
  rerender(
    <ClinicalHypotheses
      canCancel={false}
      onCancel={onCancel}
      beforeComplete={beforeComplete}
      onCompleted={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByText('common.cancel'));
  expect(onCancel).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('common.retry'));
  await waitFor(() => expect(api.complete).toHaveBeenCalledTimes(2));
  expect(api.create).toHaveBeenCalledOnce();
});





