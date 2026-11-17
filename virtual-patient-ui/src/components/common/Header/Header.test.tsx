import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {createInstance} from 'i18next';
import {I18nextProvider} from 'react-i18next';
import {Header} from './index';
import en from '../../../i18n/locales/en.json';
import es from '../../../i18n/locales/es.json';
import {loadSurvey} from '../../../services/perceptionSurvey';

const account = vi.hoisted(() => ({role: 'admin'}));
vi.mock('../../../hooks', () => ({useUser: () => ({user: account, signOut: vi.fn()})}));
vi.mock('../Menu', () => ({Menu: () => null}));
vi.mock('../HelpModal', () => ({HelpModal: () => null}));
vi.mock('../../../services/perceptionSurvey', () => ({loadSurvey: vi.fn().mockRejectedValue(new Error('unavailable'))}));
afterEach(cleanup);

it('shows the pending indicator only for an eligible unsubmitted survey', async () => {
  const i18n = createInstance();
  await i18n.init({lng: 'es', resources: {es: {translation: es}}});
  account.role = 'student';
  vi.mocked(loadSurvey).mockResolvedValueOnce({eligible: true, status: 'DRAFT', answers: {}, comments: {}, sus_score: null, questionnaire_version: null, created_at: null, submitted_at: null, updated_at: null});
  render(<I18nextProvider i18n={i18n}><MemoryRouter><Header /></MemoryRouter></I18nextProvider>);
  const link = await screen.findByRole('link', {name: /Encuesta de percepción/});
  expect(link.getAttribute('href')).toBe('/perception-survey');
  expect(within(link).getByLabelText('Encuesta pendiente de entrega')).toBeTruthy();
});

it('refreshes survey eligibility after a self-assessment is submitted', async () => {
  const i18n = createInstance();
  await i18n.init({lng: 'es', resources: {es: {translation: es}}});
  account.role = 'student';
  vi.mocked(loadSurvey)
    .mockResolvedValueOnce({eligible: false, status: 'DRAFT', answers: {}, comments: {}, sus_score: null, questionnaire_version: null, created_at: null, submitted_at: null, updated_at: null})
    .mockResolvedValueOnce({eligible: true, status: 'DRAFT', answers: {}, comments: {}, sus_score: null, questionnaire_version: null, created_at: null, submitted_at: null, updated_at: null});
  render(<I18nextProvider i18n={i18n}><MemoryRouter><Header /></MemoryRouter></I18nextProvider>);
  expect(await screen.findByRole('button', {name: 'Encuesta de percepción'})).toHaveProperty('disabled', true);
  window.dispatchEvent(new Event('perception-survey-updated'));
  expect((await screen.findByRole('link', {name: /Encuesta de percepción/})).getAttribute('href')).toBe('/perception-survey');
});

it.each(['es', 'en'])('keeps role-specific navigation order and permissions in %s', async (language) => {
  const i18n = createInstance();
  await i18n.init({lng: language, resources: {en: {translation: en}, es: {translation: es}}});
  for (const [role, destinations] of [
    ['admin', ['/cases', '/interviews', '/users']],
    ['doctor', ['/cases', '/interviews']],
    ['student', ['/cases', '/interviews']],
  ] as const) {
    account.role = role;
    const view = render(<I18nextProvider i18n={i18n}><MemoryRouter initialEntries={['/cases']}><Header /></MemoryRouter></I18nextProvider>);
    const links = within(screen.getByRole('navigation')).getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual(destinations);
    expect(links[0].textContent).toBe(i18n.t('navigation.clinicalCases'));
    if (role === 'admin') {
      expect(links[1].textContent).toBe(i18n.t('navigation.conversations'));
      expect(links[2].textContent).toBe(i18n.t('navigation.users'));
    }
    view.unmount();
  }
});

it.each([
  ['student', '/cases', '/cases'],
  ['doctor', '/cases', '/cases'],
  ['admin', '/cases', '/cases'],
  ['student', '/interviews/calibration', '/cases'],
  ['doctor', '/interviews/calibration', '/cases'],
  ['admin', '/cases/7', '/cases'],
  ['student', '/interviews', '/interviews'],
  ['doctor', '/interviews', '/interviews'],
  ['admin', '/interviews', '/interviews'],
  ['student', '/interviews/example/review', '/interviews'],
  ['doctor', '/interviews/example/review', '/interviews'],
  ['admin', '/interviews/example/review', '/interviews'],
  ['student', '/interviews/example/session', '/interviews'],
  ['doctor', '/interviews/example/session', '/interviews'],
  ['admin', '/interviews/example/session', '/interviews'],
  ['admin', '/users', '/users'],
])('marks exactly one tab for %s at %s', async (role, pathname, destination) => {
  account.role = role;
  const i18n = createInstance();
  await i18n.init({lng: 'es', resources: {es: {translation: es}}});
  render(<I18nextProvider i18n={i18n}><MemoryRouter initialEntries={[pathname]}><Header /></MemoryRouter></I18nextProvider>);
  const links = within(screen.getByRole('navigation')).getAllByRole('link');
  const active = links.filter((link) => link.getAttribute('aria-current') === 'page');
  expect(active).toHaveLength(1);
  expect(active[0].getAttribute('href')).toBe(destination);
  expect(links.filter((link) => link.classList.contains('ui-navigation-link--active'))).toEqual(active);
});

it('keeps the interviews tab selected and returns to the unified list from a teacher review', async () => {
  account.role = 'doctor';
  const i18n = createInstance();
  await i18n.init({lng: 'es', resources: {es: {translation: es}}});
  render(<I18nextProvider i18n={i18n}><MemoryRouter initialEntries={[{pathname: '/interviews/example/review', state: {navigationSection: 'assignments'}}]}><Header /></MemoryRouter></I18nextProvider>);
  expect(within(screen.getByRole('navigation')).getAllByRole('link').filter((link) => link.getAttribute('aria-current') === 'page').map((link) => link.getAttribute('href'))).toEqual(['/interviews']);
});
