// @vitest-environment jsdom
import {cleanup, render, waitFor} from '@testing-library/react';
import {Outlet} from 'react-router-dom';
import {afterEach, expect, it, vi} from 'vitest';
import {AppRouter} from './AppRouter';

const {session, getActiveInterview} = vi.hoisted(() => ({
  session: {user: null as {role: string} | null, isLoading: false},
  getActiveInterview: vi.fn(),
}));

vi.mock('./hooks/useUser', () => ({useUser: () => session}));
vi.mock('./services/interviews', () => ({getActiveInterview}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('./components/common', () => ({AppContainer: Outlet}));
vi.mock('./components/Auth/AuthLayout', () => ({AuthLayout: () => null}));
vi.mock('./components/ClinicalCases', () => ({ClinicalCases: () => null}));
vi.mock('./components/ClinicalCases/PatientPreview', () => ({PatientPreview: () => null}));
vi.mock('./components/Chats', () => ({Chats: () => null}));
vi.mock('./components/Users', () => ({Users: () => null}));
vi.mock('./components/ClinicalChat', () => ({ClinicalChat: () => null}));

afterEach(() => {
  cleanup();
  getActiveInterview.mockReset();
});

it.each([
  ['superuser', '/', null, '/cases'],
  ['student', '/', null, '/cases'],
  ['teacher', '/unknown', null, '/cases'],
  ['student', '/interviews/42/calibration', null, '/cases'],
  ['student', '/cases/123', {id: 42}, '/interviews/42/session'],
  ['teacher', '/', {id: 42}, '/interviews/42/session'],
  [null, '/unknown', null, '/welcome'],
])('routes %s from %s', async (role, entry, activeInterview, destination) => {
  session.user = role ? {role} : null;
  getActiveInterview.mockResolvedValue(activeInterview);
  window.history.replaceState(null, '', entry);

  render(<AppRouter />);

  await waitFor(() => expect(window.location.pathname).toBe(destination));
  expect(getActiveInterview).toHaveBeenCalledTimes(role && role !== 'superuser' ? 1 : 0);
});
