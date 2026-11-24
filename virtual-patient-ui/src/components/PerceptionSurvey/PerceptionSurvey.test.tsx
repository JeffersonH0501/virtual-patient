import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {PerceptionSurvey} from './index';
import {loadSurvey, saveSurvey} from '../../services/perceptionSurvey';

vi.mock('../../hooks', () => ({useUser: () => ({user: {id: 1, role: 'student'}})}));
vi.mock('react-i18next', () => ({useTranslation: () => ({i18n: {resolvedLanguage: 'es'}, t: (key: string) => key})}));
vi.mock('../../services/perceptionSurvey', () => ({loadSurvey: vi.fn(), saveSurvey: vi.fn(), cachedSurvey: () => null, clearSurveyCache: vi.fn()}));
afterEach(() => {
  cleanup(); vi.resetAllMocks();
});

const draft = {eligible: true, status: 'DRAFT' as const, answers: {}, comments: {}, sus_score: null, questionnaire_version: null, created_at: null, submitted_at: null, updated_at: null};

it('retains answers across sections and saves both sections as a draft', async () => {
  vi.mocked(loadSurvey).mockResolvedValue(draft);
  vi.mocked(saveSurvey).mockResolvedValue({...draft, answers: {'SUS-01': 5, 'EVA-01': 3}});
  render(<PerceptionSurvey />);
  const first = await screen.findByRole('radiogroup', {name: /SUS-01/});
  expect((screen.getByRole('button', {name: 'perception.save'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(within(first).getByRole('radio', {name: /5\./}));
  expect((screen.getByRole('button', {name: 'perception.submit'}) as HTMLButtonElement).disabled).toBe(true);
  const second = screen.getByRole('radiogroup', {name: /EVA-01/});
  expect(within(second).getByText('perception.criteria')).toBeTruthy();
  fireEvent.click(within(second).getByRole('radio', {name: /3\./}));
  expect((within(first).getByRole('radio', {name: /5\./}) as HTMLInputElement).checked).toBe(true);
  fireEvent.click(screen.getByRole('button', {name: 'perception.save'}));
  await waitFor(() => expect(saveSurvey).toHaveBeenCalledWith({'SUS-01': 5, 'EVA-01': 3}, {}, 'save'));
  await waitFor(() => expect((screen.getByRole('button', {name: 'perception.save'}) as HTMLButtonElement).disabled).toBe(true));
  fireEvent.click(within(first).getByRole('radio', {name: /4\./}));
  expect((screen.getByRole('button', {name: 'perception.save'}) as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(within(first).getByRole('radio', {name: /5\./}));
  expect((screen.getByRole('button', {name: 'perception.save'}) as HTMLButtonElement).disabled).toBe(true);
  const comment = screen.getAllByRole('textbox')[0];
  fireEvent.change(comment, {target: {value: 'Feedback'}});
  expect((screen.getByRole('button', {name: 'perception.save'}) as HTMLButtonElement).disabled).toBe(false);
  fireEvent.change(comment, {target: {value: ''}});
  expect((screen.getByRole('button', {name: 'perception.save'}) as HTMLButtonElement).disabled).toBe(true);
}, 15000);

it('keeps the form locked when eligibility is missing', async () => {
  vi.mocked(loadSurvey).mockResolvedValue({...draft, eligible: false});
  render(<PerceptionSurvey />);
  expect(await screen.findByText('perception.locked')).toBeTruthy();
  expect(screen.queryByRole('radiogroup')).toBeNull();
});
it('lists the SUS, experience and evaluation blocks in order with the experience dimensions grouped', async () => {
  vi.mocked(loadSurvey).mockResolvedValue(draft);
  render(<PerceptionSurvey />);
  await screen.findByRole('radiogroup', {name: /SUS-01/});
  const questions = screen.getAllByRole('radiogroup');
  const ids = questions.map((question) => /(SUS|VOZ|CON|CLI|EVA)-\d\d/.exec(question.textContent ?? '')?.[0]);
  expect(ids).toHaveLength(30);
  expect(ids[0]).toBe('SUS-01');
  expect(ids[10]).toBe('VOZ-01');
  expect(ids[18]).toBe('EVA-01');
  expect(document.querySelectorAll('.survey-group-heading')).toHaveLength(3);
  expect(within(questions[0]).getAllByRole('radio')).toHaveLength(5);
  expect(within(questions[0]).getByText('5')).toBeTruthy();
  expect(screen.queryByRole('table')).toBeNull();
  expect(screen.getAllByRole('textbox')).toHaveLength(3);
});
