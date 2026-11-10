import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {PerceptionSurvey} from './index';
import {loadSurvey, saveSurvey} from '../../services/perceptionSurvey';

vi.mock('../../hooks', () => ({useUser: () => ({user: {id: 1, role: 'student'}})}));
vi.mock('react-i18next', () => ({useTranslation: () => ({i18n: {resolvedLanguage: 'es'}, t: (key: string) => key})}));
vi.mock('../../services/perceptionSurvey', () => ({loadSurvey: vi.fn(), saveSurvey: vi.fn()}));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

const draft = {eligible: true, status: 'DRAFT' as const, answers: {}, comments: {}, cuq_score: null, created_at: null, submitted_at: null, updated_at: null};

it('retains answers across sections and saves both sections as a draft', async () => {
  vi.mocked(loadSurvey).mockResolvedValue(draft);
  vi.mocked(saveSurvey).mockResolvedValue({...draft, answers: {'CUQ-01': 5, 'EVA-01': 3}});
  render(<PerceptionSurvey />);
  const first = await screen.findByRole('row', {name: /CUQ-01/});
  expect((screen.getByRole('button', {name: 'perception.save'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(within(first).getByRole('radio', {name: /5\./}));
  expect((screen.getByRole('button', {name: 'perception.submit'}) as HTMLButtonElement).disabled).toBe(true);
  const second = screen.getByRole('row', {name: /EVA-01/});
  expect(within(second).getByText('perception.criteria')).toBeTruthy();
  fireEvent.click(within(second).getByRole('radio', {name: /3\./}));
  expect((within(screen.getByRole('row', {name: /CUQ-01/})).getByRole('radio', {name: /5\./}) as HTMLInputElement).checked).toBe(true);
  fireEvent.click(screen.getByRole('button', {name: 'perception.save'}));
  await waitFor(() => expect(saveSurvey).toHaveBeenCalledWith({'CUQ-01': 5, 'EVA-01': 3}, {}, 'save'));
  await waitFor(() => expect((screen.getByRole('button', {name: 'perception.save'}) as HTMLButtonElement).disabled).toBe(true));
  fireEvent.click(within(screen.getByRole('row', {name: /CUQ-01/})).getByRole('radio', {name: /4\./}));
  expect((screen.getByRole('button', {name: 'perception.save'}) as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(within(screen.getByRole('row', {name: /CUQ-01/})).getByRole('radio', {name: /5\./}));
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
  expect(screen.queryByRole('group')).toBeNull();
});
