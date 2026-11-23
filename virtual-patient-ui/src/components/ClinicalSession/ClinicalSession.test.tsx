import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {ClinicalSession} from '.';
import {ROUTES} from '../../utils/routes';

const navigate = vi.hoisted(() => vi.fn());
vi.mock('react-router-dom', () => ({useNavigate: () => navigate}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('../common', async () => await import('../common/CustomSelect'));
vi.mock('../../hooks/useSessionList', () => ({
  useSessionList: () => ({items: [{id: 7, name: 'Cooperative'}], loading: false}),
}));

afterEach(() => {
  cleanup();
  navigate.mockClear();
});

const selectOption = (label: string, option: string) => {
  fireEvent.click(screen.getByRole('combobox', {name: label}));
  fireEvent.click(screen.getByRole('option', {name: option}));
};

it.each(['es', 'en'] as const)('carries the selected response language to calibration (%s)', (language) => {
  render(<ClinicalSession clinicalCase={{id: 1, title: 'Case', description: '', caseType: 'default', age: null}} />);
  const languageSelect = screen.getByRole('combobox', {name: 'clinicalSession.patientResponseLanguage'});
  expect(languageSelect.textContent).toContain('clinicalSession.selectLanguage');
  expect(screen.getByRole('button', {name: 'clinicalSession.startSession'}).hasAttribute('disabled')).toBe(true);

  selectOption('clinicalSession.personality', 'Cooperative');
  selectOption('clinicalSession.gender', 'clinicalSession.female');
  const start = screen.getByRole('button', {name: 'clinicalSession.startSession'});
  expect(start.hasAttribute('disabled')).toBe(true);
  fireEvent.click(start);
  expect(navigate).not.toHaveBeenCalled();

  selectOption('clinicalSession.patientResponseLanguage', 'clinicalSession.english');
  expect(languageSelect.textContent).toContain('clinicalSession.english');
  if (language === 'es') {
    selectOption('clinicalSession.patientResponseLanguage', 'clinicalSession.spanish');
  }
  fireEvent.click(screen.getByRole('button', {name: 'clinicalSession.startSession'}));

  expect(navigate).toHaveBeenCalledWith(ROUTES.calibration, {
    state: {
      clinicalCaseId: 1,
      clinicalCaseTitle: 'Case',
      patientResponseLanguage: language,
      personalityId: 7,
      gender: 'female',
    },
  });
});
