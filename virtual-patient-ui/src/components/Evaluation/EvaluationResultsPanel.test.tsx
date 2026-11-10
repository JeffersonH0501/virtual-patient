import {afterEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import i18next from 'i18next';
import {I18nextProvider} from 'react-i18next';
import en from '../../i18n/locales/en.json';
import {EvaluationResultsPanel} from './EvaluationResultsPanel';
import {InterviewEvaluationResponse} from '../../types/evaluation';
import {requestLearningMoments} from '../../services/evaluations/learningMoments';

const fixtures = vi.hoisted(() => ({
  role: 'student',
  criteria: [
    'The doctor showed interest in the patient\'s ideas about his/her health.',
    'The doctor showed genuine interest and concern for the patient.',
    'The doctor provided the patient with information about their concerns, whenever it was within their professional competence.',
    'The doctor was considerate of the patient\'s needs and prioritized them.',
  ],
  evidence: ['Visual orientation while the patient is speaking: observable listening behavior.'],
  note: 'Observations are complementary evidence, not direct measurements of interest.',
}));

vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {role: fixtures.role}})}));
vi.mock('../../services/evaluations/learningMoments', () => ({requestLearningMoments: vi.fn(async () => ({status: 'completed', stale: false, moments: []}))}));
vi.mock('../../contexts/EvaluationAspectsContext', () => ({
  useEvaluationAspects: () => ({
    aspects: {
      showInterest: fixtures.criteria, showEmpathy: ['Original empathy criterion'],
      speakClearly: ['Original clarity criterion'], generalCommunication: ['Original general criterion'],
      completeness: ['Original completeness criterion'], openCommunication: ['Original open criterion'],
    },
    multimodalAspects: [
      {aspect: 'show_interest', criteria: fixtures.criteria, evidence: fixtures.evidence, observationNote: fixtures.note},
      {aspect: 'show_empathy', criteria: ['Original empathy criterion'], evidence: ['Listening behavior and speaking prosody'], observationNote: fixtures.note},
      {aspect: 'speak_clearly', criteria: ['Original clarity criterion'], evidence: ['Temporal speech patterns and prosodic modulation'], observationNote: fixtures.note},
    ],
    error: null,
  }),
}));

const i18n = i18next.createInstance();
await i18n.init({lng: 'en', resources: {en: {translation: en}}, interpolation: {escapeValue: false}});

const makeData = (criticalTurns = [{turnId: 'c12aba83-0d0b-47b9-b230-fb5c809f7eae', annotation: 'The response moved on without addressing the concern.'}]): InterviewEvaluationResponse => ({
  interview: {
    id: 7, publicId: 'abcdefghijk', userId: 1, clinicalCaseId: 1,
    status: 'completed', startTime: '2026-10-06T10:00:00Z', endTime: '2026-10-06T10:01:00Z',
    totalDuration: 60, createdAt: '2026-10-06T10:00:00Z',
    interviewMetadata: {}, messages: [], sessionNotes: [], isOwner: true,
    interviewEvaluation: {overallScore: 4.2},
    multimodalInterviewEvaluation: {overallScore: 3.7},
  } as InterviewEvaluationResponse['interview'],
  evaluationResults: (['general_communication', 'completeness', 'show_interest', 'show_empathy', 'speak_clearly', 'open_communication'] as const).map((aspect) => ({
    aspect, score: 4, feedback: `Original ${aspect}`, timestamp: '2026-10-06T10:01:00Z',
  })),
  multimodalEvaluationResults: (['general_communication', 'completeness', 'show_interest', 'show_empathy', 'speak_clearly', 'open_communication'] as const).map((aspect) => {
    const enriched = ['show_interest', 'show_empathy', 'speak_clearly'].includes(aspect);
    return {aspect, score: enriched ? 3.5 : 4,
      feedback: enriched ? `Multimodal ${aspect}` : `Original ${aspect}`,
      timestamp: '2026-10-06T10:01:00Z', ...(enriched ? {criticalTurns} : {})};
  }),
});

const renderPanel = (data = makeData()) => render(
  <I18nextProvider i18n={i18n}><EvaluationResultsPanel evaluationData={data} turns={Array.from({length: 4}, (_, index) => ({turnId: index === 3 ? 'c12aba83-0d0b-47b9-b230-fb5c809f7eae' : `turn-${index}`, speaker: 'patient' as const, transcript: '', inputSource: 'audio', timingSource: 'recording', timingQuality: 'measured', startMs: index * 1000}))} /></I18nextProvider>,
);

const openCriteria = (component: string) => {
  fireEvent.click(screen.getByRole('button', {name: i18n.t('evaluation.viewCriteriaFor', {component})}));
};

afterEach(() => {
  cleanup();
  fixtures.role = 'student';
});

it.each(['student', 'teacher', 'superuser'])('restricts evaluation regeneration to superusers for role %s', (role) => {
  fixtures.role = role;
  render(<I18nextProvider i18n={i18n}><EvaluationResultsPanel evaluationData={makeData()} canRegenerate onRegenerate={vi.fn()} /></I18nextProvider>);
  const button = screen.queryByRole('button', {name: en.evaluation.regenerateEvaluation});
  expect(Boolean(button)).toBe(role === 'superuser');
});

it('marks stale evaluation only on its regeneration control and exposes the explanation on hover or focus', () => {
  fixtures.role = 'superuser';
  const {rerender} = render(<I18nextProvider i18n={i18n}><EvaluationResultsPanel evaluationData={makeData()} canRegenerate evaluationStale /></I18nextProvider>);
  const button = screen.getByRole('button', {name: en.evaluation.regenerateEvaluation});
  expect(button.classList.contains('ui-icon-button--warning')).toBe(true);
  expect(button.querySelector('.evaluation-regenerate-dot')).not.toBeNull();
  expect(screen.queryByText(en.evaluation.stale)).toBeNull();
  fireEvent.mouseEnter(button.parentElement!);
  const tooltip = screen.getByRole('tooltip');
  expect(tooltip.textContent).toBe(en.evaluation.stale);
  expect(button.getAttribute('aria-describedby')).toBe(tooltip.id);
  fireEvent.mouseLeave(button.parentElement!);
  expect(screen.queryByRole('tooltip')).toBeNull();
  fireEvent.focus(button);
  expect(screen.getByRole('tooltip')).toBeTruthy();
  fireEvent.keyDown(button, {key: 'Escape'});
  expect(screen.queryByRole('tooltip')).toBeNull();
  rerender(<I18nextProvider i18n={i18n}><EvaluationResultsPanel evaluationData={makeData()} canRegenerate evaluationStale={false} /></I18nextProvider>);
  expect(button.classList.contains('ui-icon-button--warning')).toBe(false);
  expect(button.querySelector('.evaluation-regenerate-dot')).toBeNull();
});

it('regenerates only after confirmation and leaves cancellation without effects', () => {
  fixtures.role = 'superuser';
  const regenerate = vi.fn();
  render(<I18nextProvider i18n={i18n}><EvaluationResultsPanel evaluationData={makeData()} canRegenerate onRegenerate={regenerate} /></I18nextProvider>);
  fireEvent.click(screen.getByRole('button', {name: en.evaluation.regenerateEvaluation}));
  expect(regenerate).not.toHaveBeenCalled();
  expect(screen.getByRole('dialog', {name: en.evaluation.regenerateEvaluation})).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: en.common.cancel}));
  expect(regenerate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: en.evaluation.regenerateEvaluation}));
  fireEvent.click(screen.getByRole('button', {name: en.common.accept}));
  expect(regenerate).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('dialog')).toBeNull();
});

it('runs only the selected operation from the shared refresh control', () => {
  fixtures.role = 'superuser';
  const regenerate = vi.fn();
  const reprocess = vi.fn();
  render(<I18nextProvider i18n={i18n}>
    <EvaluationResultsPanel evaluationData={makeData()} canRegenerate onRegenerate={regenerate} onReprocess={reprocess} />
  </I18nextProvider>);

  const open = () => fireEvent.click(screen.getByRole('button', {name: en.evaluation.refreshActions}));
  open();
  expect(reprocess).not.toHaveBeenCalled();
  expect(regenerate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: en.clinicalChat.recap.refreshAnalysis}));
  expect(reprocess).toHaveBeenCalledOnce();
  expect(regenerate).not.toHaveBeenCalled();

  open();
  fireEvent.click(screen.getByRole('button', {name: en.evaluation.regenerateEvaluation}));
  expect(regenerate).toHaveBeenCalledOnce();
  expect(reprocess).toHaveBeenCalledOnce();
});

describe('Evaluation condition selector', () => {
  it('retains historical payloads without displaying critical turns', () => {
    const seek = vi.fn();
    const turnId = makeData().multimodalEvaluationResults![2].criticalTurns![0].turnId;
    render(<I18nextProvider i18n={i18n}><EvaluationResultsPanel evaluationData={makeData()} turns={[{turnId, speaker: 'patient', transcript: '', startMs: 16000, inputSource: 'audio', timingSource: 'recording', timingQuality: 'measured'}]} onJumpToTurn={seek} /></I18nextProvider>);
    fireEvent.click(screen.getByRole('button', {name: en.evaluation.multimodalCondition}));
    expect(screen.queryByRole('region', {name: 'Critical turns'})).toBeNull();
    expect(screen.queryByRole('region', {name: en.learningMoments.title})).toBeNull();
    expect(seek).not.toHaveBeenCalled();
  });
  it('defaults to original with all six categories, feedback and overall score', () => {
    const data = makeData();
    renderPanel(data);
    expect(screen.getByRole('button', {name: 'Original evaluation'}).getAttribute('aria-pressed')).toBe('true');
    expect(screen.queryAllByRole('rowheader')).toHaveLength(6);
    for (const result of data.evaluationResults) expect(screen.getByText(result.feedback)).toBeTruthy();
    expect(screen.getByText(en.evaluation.overallScore)).toBeTruthy();
    expect(screen.getByText('4.2')).toBeTruthy();
    expect(screen.queryByText('Multimodal show_interest')).toBeNull();
  });

  it('shows moments only under their multimodal category without replacing the table', async () => {
    vi.mocked(requestLearningMoments).mockResolvedValueOnce({
      status: 'completed', stale: false, moments: [{
        id: 'moment', category: 'show_interest', type: 'improvement',
        observation: 'The concern went unacknowledged.',
        recommendation: 'Acknowledge the concern before continuing.',
        turnIds: ['c12aba83-0d0b-47b9-b230-fb5c809f7eae'], evidenceUsed: ['text'],
      }],
    });
    renderPanel();
    fireEvent.click(screen.getByRole('button', {name: en.evaluation.multimodalCondition}));
    expect(screen.queryAllByRole('rowheader')).toHaveLength(6);
    expect(screen.getByText('Multimodal show_interest')).toBeTruthy();
    expect(screen.queryByText('Turn c12aba83-0d0b-47b9-b230-fb5c809f7eae')).toBeNull();
    expect(screen.queryByRole('region', {name: 'Critical turns'})).toBeNull();
    expect(screen.queryByRole('region', {name: en.learningMoments.title})).toBeNull();
    expect(screen.getByText(en.evaluation.overallScore)).toBeTruthy();
    expect(screen.getByText('3.7')).toBeTruthy();
    expect(screen.queryByText('4.2')).toBeNull();
    expect(screen.queryByText(en.evaluation.textBasedCategory)).toBeNull();
    for (const aspect of ['general_communication', 'completeness', 'open_communication']) {
      const article = screen.getByText(`Original ${aspect}`).closest('tr')!;
      expect(within(article).queryByRole('region', {name: 'Critical turns'})).toBeNull();
    }
    fireEvent.click(screen.getByRole('button', {name: i18n.t('evaluation.toggleFeedback', {criterion: en.evaluation.interestInPatient})}));
    const moments = await screen.findByRole('region', {name: en.learningMoments.title});
    const message = within(moments).getByText('The concern went unacknowledged. Acknowledge the concern before continuing.');
    expect(message.closest('article')?.classList.contains('ui-notice--warning')).toBe(true);
    expect(within(moments).queryByText(en.learningMoments.improvement)).toBeNull();
    expect(within(moments).getByRole('button', {name: i18n.t('evaluation.turnReference', {id: 4})})).toBeTruthy();
    expect(moments.closest('tbody')?.querySelector('th')?.textContent).toContain(en.evaluation.interestInPatient);
    expect(screen.getByRole('table')).toBeTruthy();
    expect(screen.getByText('3.7')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: 'Original evaluation'}));
    expect(screen.queryAllByRole('rowheader')).toHaveLength(6);
    expect(screen.queryByRole('region', {name: en.learningMoments.title})).toBeNull();
  });

  it('does not render empty critical turns and retains textual fallback categories', () => {
    const data = makeData([]);
    renderPanel(data);
    fireEvent.click(screen.getByRole('button', {name: en.evaluation.multimodalCondition}));
    expect(screen.queryByRole('region', {name: 'Critical turns'})).toBeNull();
    expect(screen.queryAllByRole('rowheader')).toHaveLength(6);
    expect(screen.getByText('Original general_communication')).toBeTruthy();
  });

  it('shows an explicit unavailable state for legacy interviews without multimodal results', () => {
    const data = makeData();
    delete data.multimodalEvaluationResults;
    renderPanel(data);
    fireEvent.click(screen.getByRole('button', {name: en.evaluation.multimodalCondition}));
    expect(screen.queryAllByRole('rowheader')).toHaveLength(0);
    expect(screen.getByText(en.evaluation.multimodalUnavailable)).toBeTruthy();
  });

  it('keeps criteria and sources without an extra multimodal evidence section', () => {
    renderPanel();
    openCriteria(en.evaluation.interestInPatient);
    const originalDialog = screen.getByRole('dialog', {name: en.evaluation.evaluationCriteria});
    expect(within(originalDialog).getByText(i18n.t('evaluation.evaluationBasedOn', {
      component: en.evaluation.interestInPatient,
    }))).toBeTruthy();
    for (const criterion of fixtures.criteria) expect(within(originalDialog).getByText(criterion)).toBeTruthy();
    expect(within(originalDialog).getByText('Communication Assessment Tool (CAT)')).toBeTruthy();
    expect(within(originalDialog).queryByText(en.evaluation.multimodalEvidence)).toBeNull();
    fireEvent.click(within(originalDialog).getByRole('button', {name: en.common.close}));
    fireEvent.click(screen.getByRole('button', {name: en.evaluation.multimodalCondition}));
    openCriteria(en.evaluation.interestInPatient);
    const multimodalDialog = screen.getByRole('dialog', {name: en.evaluation.evaluationCriteria});
    for (const criterion of fixtures.criteria) expect(within(multimodalDialog).getByText(criterion)).toBeTruthy();
    expect(within(multimodalDialog).queryByText(fixtures.evidence[0])).toBeNull();
    expect(within(multimodalDialog).queryByText(fixtures.note)).toBeNull();
    expect(within(multimodalDialog).getByText('Communication Assessment Tool (CAT)')).toBeTruthy();
  });

  it.each([
    [en.evaluation.understandingAndEmpathy, 'Original empathy criterion', 'Listening behavior and speaking prosody'],
    [en.evaluation.communicationClarity, 'Original clarity criterion', 'Temporal speech patterns and prosodic modulation'],
  ])('shows the %s criteria without a multimodal evidence section', (name, criterion, evidence) => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', {name: en.evaluation.multimodalCondition}));
    openCriteria(name);
    const dialog = screen.getByRole('dialog', {name: en.evaluation.evaluationCriteria});
    expect(within(dialog).getByText(criterion)).toBeTruthy();
    expect(within(dialog).queryByText(evidence)).toBeNull();
    expect(within(dialog).queryByText(fixtures.evidence[0])).toBeNull();
    expect(within(dialog).queryByText(fixtures.note)).toBeNull();
  });

  it.each([
    [en.evaluation.generalCommunication, 'Original general criterion'],
    [en.evaluation.completeness, 'Original completeness criterion'],
    [en.evaluation.openCommunication, 'Original open criterion'],
  ])('keeps %s criteria textual in both conditions', (name, criterion) => {
    renderPanel();
    for (const condition of ['Original evaluation', en.evaluation.multimodalCondition]) {
      fireEvent.click(screen.getByRole('button', {name: condition}));
      openCriteria(name);
      const dialog = screen.getByRole('dialog', {name: en.evaluation.evaluationCriteria});
      expect(within(dialog).getByText(criterion)).toBeTruthy();
      expect(within(dialog).queryByText(en.evaluation.multimodalEvidence)).toBeNull();
      expect(within(dialog).queryByText(fixtures.note)).toBeNull();
      fireEvent.click(within(dialog).getByRole('button', {name: en.common.close}));
    }
  });

  it('does not invent an overall for stored legacy partial evaluations', () => {
    const data = makeData();
    data.interview.multimodalInterviewEvaluation!.overallScore = null;
    data.multimodalEvaluationResults = data.multimodalEvaluationResults!.filter((result) => result.aspect === 'show_interest');
    renderPanel(data);
    fireEvent.click(screen.getByRole('button', {name: en.evaluation.multimodalCondition}));
    expect(screen.queryByText(en.evaluation.overallScore)).toBeNull();
    expect(screen.queryAllByRole('rowheader')).toHaveLength(1);
  });
  it('uses shared table columns and expands feedback without changing scores or criterion access', () => {
    renderPanel();
    const table = screen.getByRole('table', {name: en.evaluation.criteriaTable});
    expect(within(table).getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      en.evaluation.component, en.evaluation.score, en.conversations.action,
    ]);
    expect(within(table).getAllByRole('rowheader')).toHaveLength(6);
    const name = en.evaluation.interestInPatient;
    const toggle = screen.getByRole('button', {name: i18n.t('evaluation.toggleFeedback', {criterion: name})});
    const feedbackName = i18n.t('evaluation.feedbackForCriterion', {criterion: name});
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('region', {name: feedbackName})).toBeNull();
    const criteriaAction = screen.getByRole('button', {name: i18n.t('evaluation.viewCriteriaFor', {component: name})});
    expect(screen.getByText(name).tagName).toBe('SPAN');
    expect(criteriaAction.classList.contains('ui-icon-button')).toBe(true);
    fireEvent.click(criteriaAction);
    expect(screen.getByRole('dialog')).toBeDefined();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(screen.getByRole('button', {name: en.common.close}));
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(within(screen.getByRole('region', {name: feedbackName})).getByText('Original show_interest')).toBeDefined();
    expect(screen.queryByRole('button', {name})).toBeNull();
    fireEvent.click(toggle);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('region', {name: feedbackName})).toBeNull();
    const componentRow = screen.getByText(name).closest('tr')!;
    fireEvent.click(within(componentRow).getAllByRole('cell')[0]);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(within(screen.getByRole('region', {name: feedbackName})).queryByRole('button', {name: i18n.t('evaluation.viewCriteriaFor', {component: name})})).toBeNull();
    fireEvent.click(toggle);
    expect(screen.queryByRole('region', {name: feedbackName})).toBeNull();
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole('button', {name: en.evaluation.multimodalCondition}));
    expect(screen.getByRole('button', {name: i18n.t('evaluation.toggleFeedback', {criterion: name})}).getAttribute('aria-expanded')).toBe('false');
  });

});

it.each(['student', 'teacher', 'superuser'])('shows the case comparison inside the completeness criteria for %s', (role) => {
  fixtures.role = role;
  const data = makeData();
  data.interview.hypotheses = [{id: 1, interviewId: 7, hypothesisText: 'Synthetic hypothesis', hypothesisOrder: 1}];
  renderPanel(data);
  const row = screen.getByText(en.evaluation.completeness).closest('tr')!;
  const toggle = within(row).getByRole('button', {name: i18n.t('evaluation.toggleFeedback', {criterion: en.evaluation.completeness})});
  expect(within(row).queryByRole('button', {name: en.evaluation.clinicalCaseComparison})).toBeNull();
  openCriteria(en.evaluation.completeness);
  const dialog = screen.getByRole('dialog', {name: en.evaluation.evaluationCriteria});
  expect(within(dialog).getByRole('heading', {name: en.evaluation.clinicalCaseComparison})).toBeDefined();
  expect(within(dialog).getByText('Synthetic hypothesis')).toBeDefined();
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(row);
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  fireEvent.click(toggle.querySelector('svg')!);
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
});
