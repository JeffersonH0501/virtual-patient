import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {ClinicalCases} from './index';

const mocks = vi.hoisted(() => ({role: 'student', defaults: vi.fn()}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('../../hooks', () => ({useUser: () => ({user: {role: mocks.role}})}));
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {role: mocks.role}})}));
vi.mock('../../services/clinicalCases', () => ({
  getDefaultCases: mocks.defaults,
}));
vi.mock('./CaseCard', () => ({
  CaseCard: ({
    clinicalCase,
    caseIndex,
    expanded,
    onToggle,
  }: {
    clinicalCase: {title: string};
    caseIndex: number;
    expanded: boolean;
    onToggle: () => void;
  }) => (
    <button aria-expanded={expanded} onClick={onToggle}>
      {caseIndex}: {clinicalCase.title}
    </button>
  ),
}));
beforeEach(() => {
  mocks.role = 'student';
  mocks.defaults
    .mockReset()
    .mockResolvedValue(
      Array.from({length: 5}, (_, index) => ({id: index + 1, title: 'Default ' + (index + 1)})),
    );
});
afterEach(cleanup);
it('shows default cases without a surrounding list panel or pagination', async () => {
  render(
    <MemoryRouter>
      <ClinicalCases />
    </MemoryRouter>,
  );
  await screen.findByText('5: Default 5');
  expect(screen.getByText('1: Default 1')).toBeDefined();
  expect(screen.queryByRole('navigation')).toBeNull();
  expect(screen.queryByText('Create case')).toBeNull();
  fireEvent.click(screen.getByText('1: Default 1'));
  expect(screen.getByText('1: Default 1').getAttribute('aria-expanded')).toBe('true');
});
it.each(['student', 'teacher', 'superuser'])('keeps test actions inside individual cases (%s)', async (role) => {
  mocks.role = role;
  render(
    <MemoryRouter>
      <ClinicalCases />
    </MemoryRouter>,
  );
  await screen.findByText('5: Default 5');
  expect(screen.queryByText('Create case')).toBeNull();
  expect(screen.queryByText(/Custom case/)).toBeNull();
  expect(screen.queryByRole('button', {name: 'patientPreview.title'})).toBeNull();
});
