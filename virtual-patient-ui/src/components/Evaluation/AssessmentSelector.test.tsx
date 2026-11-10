import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {AssessmentSelector} from './AssessmentSelector';
import {InterviewEvaluationResponse} from '../../types/evaluation';

const mocks = vi.hoisted(() => ({role: 'superuser', request: vi.fn()}));
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {id: 3, role: mocks.role}})}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: {name?: string}) => key === 'grading.teacherEvaluation' ? 'Evaluación ' + values?.name : key,
  }),
}));
vi.mock('../../services/teacherGrading', () => ({gradingRequest: mocks.request}));
vi.mock('../../contexts/EvaluationAspectsContext', () => ({
  useEvaluationAspects: () => ({aspects: [], multimodalAspects: []}),
}));
vi.mock('../../services/evaluations/learningMoments', () => ({
  requestLearningMoments: vi.fn(async () => ({status: 'completed', stale: false, moments: []})),
}));
vi.mock('../Students/AssignmentDialog', () => ({
  AssignmentDialog: ({onClose, onSaved}: {onClose: () => void; onSaved?: () => void}) => (
    <div role="dialog">
      <button onClick={onClose}>Close</button>
      <button
        onClick={() => {
          onSaved?.();
          onClose();
        }}
      >
        Save
      </button>
    </div>
  ),
}));

const timestamp = '2026-10-20T12:00:00Z';
const reviewers = [
  {
    assignmentId: 12,
    teacherId: 2,
    teacherName: 'Pending teacher',
    ratingId: null,
    status: 'pending',
  },
  {
    assignmentId: 13,
    teacherId: 3,
    teacherName: 'Submitted teacher',
    ratingId: 101,
    status: 'submitted',
  },
];
const ratings = [
  {
    id: 101,
    teacherName: 'Submitted teacher',
    overallScore: 2.5,
    submittedAt: timestamp,
    results: [{aspect: 'show_interest', score: 2.5, feedback: 'Teacher feedback', timestamp}],
  },
];
const makeData = (id = 42) =>
  ({
    interview: {
      id,
      interviewEvaluation: {overallScore: 4.2},
      multimodalInterviewEvaluation: {overallScore: 3.7},
    },
    evaluationResults: [
      {aspect: 'show_interest', score: 4.2, feedback: 'Text-based feedback', timestamp},
    ],
    multimodalEvaluationResults: [
      {aspect: 'show_interest', score: 3.7, feedback: 'Multimodal feedback', timestamp},
    ],
  }) as unknown as InterviewEvaluationResponse;

beforeEach(() => {
  mocks.role = 'superuser';
  mocks.request
    .mockReset()
    .mockImplementation(async (path: string) =>
      path.endsWith('/reviewers') ? reviewers : ratings,
    );
});
afterEach(cleanup);

const sourceButtons = async () => {
  const group = screen.getByRole('group', {name: 'grading.evaluationSource'});
  await within(group).findByRole('button', {name: mocks.role === 'superuser' ? 'Evaluación Pending teacher' : 'grading.yourEvaluation'});
  return group;
};
const chooseSource = (group: HTMLElement, name: string | RegExp) => {
  fireEvent.click(within(group).getByRole('button', {name: typeof name === 'string' && name.endsWith('teacher') ? 'Evaluación ' + name : name}));
};
const activeSource = (group: HTMLElement) =>
  within(group).getByRole('button', {pressed: true});

it('places source buttons below the title with automatic modes followed by named teachers', async () => {
  render(<AssessmentSelector evaluationData={makeData()} />);
  const select = await sourceButtons();
  const panel = screen.getByRole('region', {name: 'evaluation.interviewEvaluationResults'});
  expect(within(panel.querySelector('header')!).queryByRole('group')).toBeNull();
  expect(screen.getAllByRole('group')).toHaveLength(1);
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(
    within(select)
      .getAllByRole('button')
      .map((option) => option.textContent),
  ).toEqual([
    'grading.automaticTextBased',
    'grading.automaticMultimodalEvidence',
    'Evaluación Pending teacher',
    'Evaluación Submitted teacher',
  ]);
  chooseSource(select, 'grading.automaticMultimodalEvidence');
  expect(screen.getByText('Multimodal feedback')).toBeDefined();
  expect(screen.queryByText('Text-based feedback')).toBeNull();
});

it('switches between both automatic conditions and submitted or pending teacher grades without fabricated zeros', async () => {
  render(<AssessmentSelector evaluationData={makeData()} canRegenerate onRegenerate={vi.fn()} />);
  const select = await sourceButtons();
  chooseSource(select, 'Pending teacher');
  expect(screen.getByText('grading.ratingPending')).toBeDefined();
  expect(screen.queryByText('0.0')).toBeNull();
  expect(screen.queryByRole('button', {name: 'evaluation.regenerateEvaluation'})).toBeNull();
  chooseSource(select, 'Submitted teacher');
  expect(screen.getByText('Teacher feedback')).toBeDefined();
  expect(screen.getAllByText('2.5')).toHaveLength(2);
  chooseSource(select, 'grading.automaticMultimodalEvidence');
  expect(screen.getByText('Multimodal feedback')).toBeDefined();
  chooseSource(select, 'grading.automaticTextBased');
  expect(screen.getByText('Text-based feedback')).toBeDefined();
  expect(mocks.request).toHaveBeenCalledTimes(2);
});

it('expands own-rating feedback and edits through the pencil beside the score without a dialog', async () => {
  mocks.role = 'teacher';
  let savedScore = 2.5;
  const aspects = [
    'coherence',
    'show_interest',
    'show_empathy',
    'speak_clearly',
    'open_communication',
    'completeness',
  ];
  mocks.request.mockImplementation(async (path: string, method?: string) => {
    if (method === 'POST') savedScore = 4;
    if (path.startsWith('/teacher-assignments/13')) {
      return {
        status: 'submitted',
        rubric: Object.fromEntries(aspects.map((aspect) => [aspect, ['Criterion']])),
        results: aspects.map((aspect) => ({
          aspect,
          score: aspect === 'show_interest' ? savedScore : 2.5,
          feedback: 'Teacher feedback',
        })),
      };
    }
    return path.endsWith('/reviewers')
      ? reviewers
      : [
          {
            ...ratings[0],
            overallScore: savedScore === 4 ? 2.8 : 2.5,
            results: [{...ratings[0].results[0], score: savedScore}],
          },
        ];
  });
  render(<AssessmentSelector evaluationData={makeData()} />);
  const select = await sourceButtons();
  expect(screen.queryByRole('button', {name: 'grading.editScore'})).toBeNull();
  expect(within(select).getAllByRole('button')).toHaveLength(2);
  const ownOption = screen.getByRole('button', {name: 'grading.yourEvaluation'});
  fireEvent.click(ownOption);
  const edit = screen.getByRole('button', {name: 'grading.editScore'});
  expect(edit.querySelector('.lucide-pencil')).not.toBeNull();
  expect(edit.previousElementSibling?.classList.contains('evaluation-score')).toBe(true);
  const disclosure = screen.getByRole('button', {name: 'evaluation.toggleFeedback'});
  expect(disclosure.getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(disclosure);
  expect(disclosure.getAttribute('aria-expanded')).toBe('true');
  expect(edit.closest('tr')?.nextElementSibling?.getAttribute('aria-hidden')).toBeNull();
  edit.focus();
  fireEvent.click(edit);
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.queryByRole('table')).toBeNull();
  expect(screen.queryByText('evaluation.overallScore')).toBeNull();
  let editor = screen.getByRole('region', {name: 'grading.editScore'});
  const cancelledScore = await within(editor).findByRole('spinbutton');
  fireEvent.change(cancelledScore, {target: {value: '1'}});
  expect(mocks.request.mock.calls.some(([, method]) => method === 'POST')).toBe(false);
  fireEvent.click(within(editor).getByRole('button', {name: 'common.cancel'}));
  expect(screen.getByRole('table')).toBeDefined();
  expect(
    screen.getByRole('button', {name: 'evaluation.toggleFeedback'}).getAttribute('aria-expanded'),
  ).toBe('true');
  expect(mocks.request.mock.calls.some(([, method]) => method === 'POST')).toBe(false);
  const reopened = screen.getByRole('button', {name: 'grading.editScore'});
  expect(document.activeElement).toBe(reopened);
  fireEvent.click(reopened);
  editor = screen.getByRole('region', {name: 'grading.editScore'});
  const score = await within(editor).findByRole('spinbutton');
  expect((score as HTMLInputElement).value).toBe('2.5');
  const save = within(editor).getByRole<HTMLButtonElement>('button', {name: 'common.save'});
  expect(save.disabled).toBe(true);
  fireEvent.change(score, {target: {value: '3'}});
  expect(save.disabled).toBe(false);
  fireEvent.change(score, {target: {value: '2.5'}});
  expect(save.disabled).toBe(true);
  expect(within(editor).queryByRole('radiogroup')).toBeNull();
  const criteria = within(editor).getByText('evaluation.evaluationCriteria').closest('summary')!;
  expect(criteria.getAttribute('aria-expanded')).toBe('true');
  expect(editor.querySelectorAll('.rating-criteria-list > li')).toHaveLength(1);
  expect(editor.querySelector('.rating-component-criteria')?.textContent).toContain('Criterion');
  fireEvent.click(criteria);
  expect(criteria.getAttribute('aria-expanded')).toBe('false');
  expect(within(editor).queryByText('grading.scoreHint')).toBeNull();
  fireEvent.change(score, {target: {value: '3.75'}});
  expect(
    (within(editor).getByRole('button', {name: 'common.save'}) as HTMLButtonElement).disabled,
  ).toBe(false);
  fireEvent.change(score, {target: {value: '6'}});
  expect(
    (within(editor).getByRole('button', {name: 'common.save'}) as HTMLButtonElement).disabled,
  ).toBe(true);
  const comment = within(editor).getByRole('textbox') as HTMLTextAreaElement;
  expect(comment.required).toBe(true);
  fireEvent.change(comment, {target: {value: '   '}});
  expect(
    (within(editor).getByRole('button', {name: 'common.save'}) as HTMLButtonElement).disabled,
  ).toBe(true);
  fireEvent.change(comment, {target: {value: 'Revised comment'}});
  fireEvent.change(score, {target: {value: '4'}});
  mocks.request.mockRejectedValueOnce(new Error('Synthetic failure'));
  fireEvent.click(within(editor).getByRole('button', {name: 'common.save'}));
  await within(editor).findByRole('alert');
  expect((score as HTMLInputElement).value).toBe('4');
  expect(comment.value).toBe('Revised comment');
  expect(screen.queryByRole('table')).toBeNull();
  fireEvent.click(within(editor).getByRole('button', {name: 'common.save'}));
  await waitFor(() => expect(screen.queryByRole('region', {name: 'grading.editScore'})).toBeNull());
  await waitFor(() => expect(screen.getByText('4.0')).toBeDefined());
  const saved = mocks.request.mock.calls.find(([, method]) => method === 'POST')![2].results;
  expect(saved).toHaveLength(6);
  expect(saved.find((entry: {aspect: string}) => entry.aspect === 'show_interest').score).toBe(4);
  expect(
    saved
      .filter((entry: {aspect: string}) => entry.aspect !== 'show_interest')
      .every((entry: {score: number}) => entry.score === 2.5),
  ).toBe(true);
});

it('keeps assignment last and opens it without replacing the selected teacher result', async () => {
  render(<AssessmentSelector canAssignTeachers evaluationData={makeData()} />);
  const select = await sourceButtons();
  chooseSource(select, 'Submitted teacher');
  expect(within(select).queryByRole('button', {name: 'grading.assignTeacher'})).toBeNull();
  fireEvent.click(screen.getByRole('button', {name: 'grading.assignTeacher'}));
  expect(screen.getByRole('dialog')).toBeDefined();
  expect(activeSource(select).textContent).toContain('Submitted teacher');
  expect(screen.getByText('Teacher feedback')).toBeDefined();
  fireEvent.click(screen.getByRole('button', {name: 'Close'}));
  expect(screen.queryByRole('dialog')).toBeNull();
});

it.each(['teacher'])(
  'defaults to multimodal and hides the text-based assessment and assignment for role %s',
  async (role) => {
    mocks.role = role;
    render(<AssessmentSelector canAssignTeachers evaluationData={makeData()} />);
    const select = await sourceButtons();
    expect(activeSource(select).textContent).toContain('grading.automaticEvaluation');
    const options = within(select);
    expect(screen.queryByRole('button', {name: 'grading.assignTeacher'})).toBeNull();
    expect(options.queryByRole('button', {name: 'grading.automaticTextBased'})).toBeNull();
  },
);

it('requires the assignment capability for a superuser', async () => {
  render(<AssessmentSelector evaluationData={makeData()} />);
  await sourceButtons();
  expect(
    screen.queryByRole('button', {name: 'grading.assignTeacher'}),
  ).toBeNull();
});

it.each(['student', 'teacher'])('shows only automatic and own self-assessment for an interview owner with role %s', async (role) => {
  mocks.role = role;
  const data = makeData();
  data.interview.isOwner = true;
  mocks.request.mockResolvedValue({status: 'submitted', rubric: {}, overallScore: 2.5,
    results: [{...ratings[0].results[0], feedback: 'Self feedback'}]});
  render(<AssessmentSelector evaluationData={data} />);
  const group = screen.getByRole('group', {name: 'grading.evaluationSource'});
  const own = await within(group).findByRole('button', {name: 'grading.selfAssessment'});
  expect(within(group).getAllByRole('button').map((button) => button.textContent)).toEqual([
    'grading.automaticEvaluation', 'grading.selfAssessment',
  ]);
  expect(group.classList.contains('justify-center')).toBe(true);
  expect(group.classList.contains('flex-wrap')).toBe(true);
  fireEvent.click(own);
  expect(await screen.findByText('Self feedback')).toBeTruthy();
  expect(mocks.request).toHaveBeenCalledExactlyOnceWith('/medical-interviews/42/self-rating');
  expect(screen.queryByRole('button', {name: 'common.previous'})).toBeNull();
  expect(screen.queryByRole('button', {name: 'common.next'})).toBeNull();
});

it('keeps automatic sources and assignment available when no teachers are assigned', async () => {
  mocks.request.mockResolvedValue([]);
  render(<AssessmentSelector canAssignTeachers evaluationData={makeData()} />);
  await waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(2));
  const select = screen.getByRole('group');
  expect(
    within(select)
      .getAllByRole('button')
      .map((option) => option.textContent),
  ).toEqual(['grading.automaticTextBased', 'grading.automaticMultimodalEvidence']);
  expect(screen.getByText('Text-based feedback')).toBeDefined();
  fireEvent.click(screen.getByRole('button', {name: 'grading.assignTeacher'}));
  expect(screen.getByRole('dialog')).toBeDefined();
  expect(activeSource(select).textContent).toContain('grading.automaticTextBased');
});

it('falls back to the text-based assessment when the selected teacher assignment is removed', async () => {
  render(<AssessmentSelector canAssignTeachers evaluationData={makeData()} />);
  const select = await sourceButtons();
  chooseSource(select, 'Submitted teacher');
  fireEvent.click(screen.getByRole('button', {name: 'grading.assignTeacher'}));
  mocks.request.mockImplementation(async (path: string) =>
    path.endsWith('/reviewers') ? [reviewers[0]] : ratings,
  );
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
  await waitFor(() => expect(activeSource(select).textContent).toContain('grading.automaticTextBased'));
  expect(screen.getByText('Text-based feedback')).toBeDefined();
  expect(screen.queryByText('Teacher feedback')).toBeNull();
});

it('resets source selection and teacher data when the interview changes', async () => {
  const view = render(<AssessmentSelector evaluationData={makeData()} />);
  const select = await sourceButtons();
  chooseSource(select, 'Submitted teacher');
  view.rerender(<AssessmentSelector evaluationData={makeData(43)} />);
  expect(activeSource(screen.getByRole('group')).textContent).toContain('grading.automaticTextBased');
  await waitFor(() =>
    expect(mocks.request).toHaveBeenCalledWith('/medical-interviews/43/reviewers'),
  );
  expect(screen.queryByText('Teacher feedback')).toBeNull();
});

it('retains automatic results and retries when teacher sources fail to load', async () => {
  mocks.request.mockRejectedValueOnce(new Error('Unavailable'));
  render(<AssessmentSelector evaluationData={makeData()} />);
  expect(await screen.findByRole('alert')).toBeDefined();
  expect(screen.getByText('Text-based feedback')).toBeDefined();
  fireEvent.click(screen.getByRole('button', {name: 'common.retry'}));
  await sourceButtons();
  expect(screen.queryByRole('alert')).toBeNull();
});
