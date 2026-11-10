import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {useState} from 'react';
import {CaseCard} from './CaseCard';
import {getClinicalCaseById} from '../../services/clinicalCases';

const actor = vi.hoisted(() => ({role: 'student'}));
vi.mock('../../hooks', () => ({useUser: () => ({user: actor})}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('../ClinicalSession', () => ({
  ClinicalSession: ({onView}: {onView?: () => void}) => (
    <div>Simulation configuration{onView && <button onClick={onView}>View</button>}</div>
  ),
}));
vi.mock('../../services/clinicalCases', () => ({getClinicalCaseById: vi.fn(async () => ({title: 'Full case', age: 65, chiefComplaint: 'Patient concern'}))}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const CasePreview = () => {
  const [expanded, setExpanded] = useState(false);
  return <CaseCard clinicalCase={{id: 7, title: 'Default case', description: 'Patient scenario', caseType: 'default'}} caseIndex={1} expanded={expanded} onToggle={() => setExpanded(!expanded)} />;
};

it.each(['student', 'teacher', 'superuser'])('uses the same disclosure card for role %s while preserving simulation access', async (role) => {
  actor.role = role;
  render(<MemoryRouter><CasePreview /></MemoryRouter>);
  const toggle = screen.getByRole('button');
  const card = screen.getByText('Patient scenario').closest('article')!;
  expect(card.classList.contains('bg-brand-50')).toBe(true);
  expect(toggle.classList.contains('case-disclosure-row')).toBe(true);
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(toggle);
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  expect(card.classList.contains('bg-white')).toBe(true);
  expect(screen.getByText('Simulation configuration')).toBeTruthy();
  expect(Boolean(screen.queryByRole('button', {name: 'View'}))).toBe(role === 'superuser');
  expect(getClinicalCaseById).not.toHaveBeenCalled();
  fireEvent.click(toggle);
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
});

it('toggles from the case number, description and chevron without toggling from the expanded content', () => {
  actor.role = 'student';
  render(<MemoryRouter><CasePreview /></MemoryRouter>);
  const toggle = screen.getByRole('button');
  expect(toggle.tagName).toBe('BUTTON');
  expect(toggle.querySelector('button')).toBeNull();
  fireEvent.click(screen.getByText('01'));
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  fireEvent.click(screen.getByText('Patient scenario'));
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(toggle.querySelector('svg')!);
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  fireEvent.click(screen.getByText('Simulation configuration'));
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  fireEvent.click(toggle);
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
});

it('loads complete details in the reading dialog only after View', async () => {
  actor.role = 'superuser';
  render(<MemoryRouter><CasePreview /></MemoryRouter>);
  expect(getClinicalCaseById).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'clinicalCases.configureCase'}));
  fireEvent.click(screen.getByRole('button', {name: 'View'}));
  const dialog = within(await screen.findByRole('dialog'));
  expect(await dialog.findByText('Full case')).toBeTruthy();
  expect(dialog.getByText('Patient concern')).toBeTruthy();
  expect(dialog.getByText('Patient concern').closest('.dialog-reading-section')).toBeTruthy();
  expect(getClinicalCaseById).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('link')).toBeNull();
});

it('keeps loading errors inside the dialog and retries without navigation', async () => {
  actor.role = 'superuser';
  vi.mocked(getClinicalCaseById).mockRejectedValueOnce(new Error('Unavailable'));
  render(<MemoryRouter><CasePreview /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', {name: 'clinicalCases.configureCase'}));
  fireEvent.click(screen.getByRole('button', {name: 'View'}));
  expect(await screen.findByRole('alert')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'common.retry'}));
  expect(await screen.findByText('Full case')).toBeTruthy();
  expect(getClinicalCaseById).toHaveBeenCalledTimes(2);
});
