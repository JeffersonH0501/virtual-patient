import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {HumanRatingPanel} from './HumanRatingPanel';
import type {CompleteInterviewResponse} from '../../types/interview';

const request = vi.hoisted(() => vi.fn());
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {id: 1, role: 'teacher'}})}));
vi.mock('../../services/teacherGrading', () => ({gradingRequest: request}));
vi.mock('../../contexts/EvaluationAspectsContext', () => ({
  useEvaluationAspects: () => ({aspects: {}, multimodalAspects: []}),
}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
const rubric = Object.fromEntries(
  [
    'coherence',
    'show_interest',
    'show_empathy',
    'speak_clearly',
    'open_communication',
    'completeness',
  ].map((key) => [key, ['Original criterion ' + key]]),
);
const workspace = {id: 1, status: 'pending', rubric, results: []};
beforeEach(() => {
  request.mockReset().mockResolvedValue(workspace);
});
afterEach(cleanup);

it('hides the criteria button in the grading table', async () => {
  const interview = {
    id: 7,
    clinicalCase: {},
    reviewAccess: {canViewAssessments: false},
  } as CompleteInterviewResponse;
  render(<HumanRatingPanel interview={interview} assignmentId={1} onSubmitted={vi.fn()} />);
  const category = await screen.findByRole('rowheader', {name: /evaluation.completeness/});
  expect(within(category).queryByRole('button', {name: 'evaluation.viewCriteriaFor'})).toBeNull();
});

it('shows the private rubric table immediately and starts grading from its pencil', async () => {
  const interview = {id: 7, reviewAccess: {canViewAssessments: false}} as CompleteInterviewResponse;
  render(<HumanRatingPanel interview={interview} assignmentId={1} onSubmitted={vi.fn()} />);
  const table = await screen.findByRole('table');
  expect(within(table).getAllByRole('rowheader')).toHaveLength(6);
  expect(screen.getByRole('heading', {name: 'evaluation.interviewEvaluationResults'})).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'grading.start'})).toBeNull();
  const row = within(table).getAllByRole('rowheader')[0].closest('tr')!;
  expect(within(row).queryByRole('button', {name: 'evaluation.toggleFeedback'})).toBeNull();
  request.mockResolvedValue({...workspace, status: 'in_progress'});
  fireEvent.click(within(row).getByRole('button', {name: 'grading.editScore'}));
  const score = await screen.findByRole('spinbutton');
  const save = screen.getByRole<HTMLButtonElement>('button', {name: 'common.save'});
  expect(save.disabled).toBe(true);
  fireEvent.change(screen.getByRole('textbox'), {target: {value: 'Draft comment'}});
  expect(save.disabled).toBe(true);
  fireEvent.change(score, {target: {value: '6'}});
  expect(save.disabled).toBe(true);
  fireEvent.change(score, {target: {value: '0'}});
  expect(save.disabled).toBe(false);
  expect(request).toHaveBeenLastCalledWith('/teacher-assignments/1/start', 'POST', undefined);
  request.mockResolvedValue({...workspace, status: 'in_progress', results: [
    {aspect: 'completeness', score: 0, feedback: 'Draft comment'},
  ]});
  fireEvent.click(screen.getByRole('button', {name: 'common.save'}));
  await screen.findByLabelText('0.0/5');
  expect(screen.queryByRole('status')).toBeNull();
  expect(request).toHaveBeenLastCalledWith('/teacher-assignments/1/draft', 'PUT', {
    results: expect.arrayContaining([{aspect: 'completeness', score: 0, feedback: 'Draft comment'}]),
  });
  expect(screen.getByLabelText('0.0/5')).toBeTruthy();
  const toggle = screen.getByRole('button', {name: 'evaluation.toggleFeedback'});
  fireEvent.click(toggle);
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
});

it.each(['assigned', 'self'])('requires all six scores and nonblank comments for %s submission, including valid zero', async (mode) => {
  const submitted = vi.fn();
  render(<HumanRatingPanel assignmentId={mode === 'assigned' ? 1 : undefined} selfInterviewId={mode === 'self' ? 7 : undefined} onSubmitted={submitted} />);
  await screen.findByRole('button', {name: 'grading.start'});
  expect(screen.getByText('grading.completeBeforeAutomaticEvaluation').classList.contains('ui-notice')).toBe(true);
  expect(request).toHaveBeenCalledTimes(1);
  request.mockResolvedValue({...workspace, status: 'in_progress'});
  fireEvent.click(screen.getByRole('button', {name: 'grading.start'}));
  const scores = await screen.findAllByRole('spinbutton');
  expect((screen.getByRole('button', {name: 'grading.submit'}) as HTMLButtonElement).disabled).toBe(
    true,
  );
  scores.forEach((score, index) => fireEvent.change(score, {target: {value: index ? '4.5' : '0'}}));
  expect((screen.getByRole('button', {name: 'grading.submit'}) as HTMLButtonElement).disabled).toBe(
    true,
  );
  const comments = screen.getAllByRole('textbox');
  comments.forEach((comment) =>
    fireEvent.change(comment, {target: {value: 'Independent rationale'}}),
  );
  fireEvent.change(comments[0], {target: {value: '  \n '}});
  expect((screen.getByRole('button', {name: 'grading.submit'}) as HTMLButtonElement).disabled).toBe(
    true,
  );
  fireEvent.change(comments[0], {target: {value: '  Independent rationale  '}});
  request.mockResolvedValue({...workspace, status: 'submitted'});
  fireEvent.click(screen.getByRole('button', {name: 'grading.submit'}));
  expect(screen.queryByRole('dialog')).toBeNull();
  await waitFor(() => expect(submitted).toHaveBeenCalledTimes(1));
  const sent = request.mock.calls.at(-1)!;
  expect(sent[0]).toBe(mode === 'self' ? '/medical-interviews/7/self-rating/submit' : '/teacher-assignments/1/submit');
  expect(sent[2].results).toHaveLength(6);
  expect(sent[2].results[0].score).toBe(0);
  expect(sent[2].results[0].feedback).toBe('Independent rationale');
});

it('edits completed ratings and saves all six scores while keeping the form available', async () => {
  const completed = {
    ...workspace,
    status: 'submitted',
    results: Object.keys(rubric).map((aspect) => ({
      aspect,
      score: 3,
      feedback: 'Previous comment',
    })),
  };
  request.mockResolvedValue(completed);
  const updated = vi.fn();
  render(<HumanRatingPanel assignmentId={1} onSubmitted={updated} />);
  const scores = await screen.findAllByRole('spinbutton');
  expect(screen.queryByRole('button', {name: 'grading.saveDraft'})).toBeNull();
  expect(screen.queryByText('grading.blind')).toBeNull();
  fireEvent.change(scores[0], {target: {value: '0'}});
  fireEvent.change(screen.getAllByRole('textbox')[0], {target: {value: 'Revised comment'}});
  fireEvent.click(screen.getByRole('button', {name: 'common.save'}));
  await screen.findByText('grading.ratingSaved');
  expect(updated).toHaveBeenCalledTimes(1);
  expect(request).toHaveBeenLastCalledWith('/teacher-assignments/1/submit', 'POST', {
    results: expect.arrayContaining([{aspect: 'coherence', score: 0, feedback: 'Revised comment'}]),
  });
  expect(screen.getAllByRole('spinbutton')).toHaveLength(6);
});

it('loads a private draft and preserves values after a recoverable save error', async () => {
  request.mockResolvedValue({
    ...workspace,
    status: 'in_progress',
    results: [{aspect: 'coherence', score: 2.5, feedback: 'Draft rationale'}],
  });
  render(<HumanRatingPanel assignmentId={1} onSubmitted={vi.fn()} />);
  const scores = await screen.findAllByRole('spinbutton');
  expect((scores[0] as HTMLInputElement).value).toBe('2.5');
  fireEvent.change(scores[0], {target: {value: '3.5'}});
  request.mockRejectedValueOnce(new Error('Synthetic failure'));
  fireEvent.click(screen.getByRole('button', {name: 'grading.saveDraft'}));
  await screen.findByRole('alert');
  expect((scores[0] as HTMLInputElement).value).toBe('3.5');
  expect((screen.getAllByRole('textbox')[0] as HTMLTextAreaElement).value).toBe('Draft rationale');
  fireEvent.click(screen.getByRole('button', {name: 'grading.saveDraft'}));
  await waitFor(() => expect(screen.getByRole<HTMLButtonElement>('button', {name: 'grading.saveDraft'}).disabled).toBe(false));
  expect(screen.queryByRole('status')).toBeNull();
});

it.each(['assigned', 'self'])('opens source case and submitted hypotheses for %s completeness assessment', async (mode) => {
  request.mockImplementation(async (path: string) => path.endsWith('/clinical-case')
    ? {title: 'Full source case', chiefComplaint: 'Synthetic source complaint'}
    : path.endsWith('/hypotheses') ? [{id: 2, hypothesisOrder: 2, hypothesisText: 'Second hypothesis'}, {id: 1, hypothesisOrder: 1, hypothesisText: 'First hypothesis'}]
    : {...workspace, interviewId: 7, status: 'in_progress'});
  render(<HumanRatingPanel assignmentId={mode === 'assigned' ? 1 : undefined}
    selfInterviewId={mode === 'self' ? 7 : undefined} aspectToEdit="completeness" onSubmitted={vi.fn()} />);
  const criterion = await screen.findByText('Original criterion completeness');
  const criteria = screen.getByRole('region', {name: 'evaluation.evaluationCriteria'});
  expect(criteria.querySelector('details, summary, [aria-expanded]')).toBeNull();
  const link = within(criteria).getByRole('button', {name: 'grading.viewFullClinicalCase'});
  expect(link.classList.contains('underline')).toBe(true);
  expect(link.compareDocumentPosition(criterion)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  fireEvent.change(screen.getByRole('spinbutton'), {target: {value: '3'}});
  fireEvent.change(screen.getByRole('textbox'), {target: {value: 'Unsaved rationale'}});
  fireEvent.click(link);
  const dialog = await screen.findByRole('dialog');
  expect(await within(dialog).findByText('Full source case')).toBeTruthy();
  expect(within(dialog).getByText('Synthetic source complaint')).toBeTruthy();
  expect(request).toHaveBeenLastCalledWith('/medical-interviews/7/clinical-case');
  fireEvent.click(within(dialog).getByRole('button', {name: 'common.close'}));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('3');
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Unsaved rationale');
  const hypothesesLink = within(criteria).getByRole('button', {name: 'grading.viewSubmittedHypotheses'});
  expect(hypothesesLink.classList.contains('underline')).toBe(true);
  expect(link.compareDocumentPosition(hypothesesLink)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  fireEvent.click(hypothesesLink);
  const hypothesesDialog = await screen.findByRole('dialog');
  expect((await within(hypothesesDialog).findAllByRole('listitem')).map((item) => item.textContent)).toEqual(['First hypothesis', 'Second hypothesis']);
  expect(request).toHaveBeenLastCalledWith('/medical-interviews/7/hypotheses');
  fireEvent.click(within(hypothesesDialog).getByRole('button', {name: 'common.close'}));
  expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Unsaved rationale');
});

it('keeps other categories visible without the completeness case link', async () => {
  request.mockResolvedValue({...workspace, interviewId: 7, status: 'in_progress'});
  render(<HumanRatingPanel assignmentId={1} aspectToEdit="show_interest" onSubmitted={vi.fn()} />);
  await screen.findByText('Original criterion show_interest');
  expect(screen.queryByRole('button', {name: 'grading.viewFullClinicalCase'})).toBeNull();
  expect(document.querySelector('details, summary')).toBeNull();
});
