import {act, cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, expect, it, vi} from 'vitest';
import {AppContainer} from '.';
import type {PropsWithChildren} from 'react';

const session = vi.hoisted(() => ({user: null as {id: number; role: string} | null, isLoading: true}));
const active = vi.hoisted(() => vi.fn());
vi.mock('../../../services/interviews', () => ({getActiveInterview: active}));
vi.mock('../../../hooks/useUser', () => ({useUser: () => session}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('../../../contexts/SessionLists', () => ({SessionListsProvider: ({children}: PropsWithChildren) => <>{children}</>}));
vi.mock('../../../contexts/InterviewMediaContext', () => ({InterviewMediaProvider: ({children}: PropsWithChildren) => <>{children}</>}));
vi.mock('../Motion', () => ({MotionContent: ({children}: PropsWithChildren) => <>{children}</>}));
vi.mock('../Header', () => ({Header: () => <header>Application header</header>}));
vi.mock('../Footer', () => ({Footer: () => null}));

afterEach(() => {
cleanup(); session.user = null; session.isLoading = true;
});

it('redirects a direct visit without ever mounting the protected page', async () => {
  const Interviews = vi.fn(() => <h1>Private interviews</h1>);
  const routes = () => (
    <MemoryRouter initialEntries={['/interviews']}>
      <Routes>
        <Route element={<AppContainer />}>
          <Route path="/interviews" element={<Interviews />} />
        </Route>
        <Route path="/welcome" element={<h1>Sign in</h1>} />
      </Routes>
    </MemoryRouter>
  );

  const view = render(routes());
  expect(screen.getByRole('status', {name: 'common.loading'}).getAttribute('aria-busy')).toBe('true');
  expect(screen.getByText('common.loading')).toBeDefined();
  expect(Interviews).not.toHaveBeenCalled();

  session.isLoading = false;
  view.rerender(routes());

  await screen.findByRole('heading', {name: 'Sign in'});
  expect(Interviews).not.toHaveBeenCalled();
});

it.each([
  ['/interviews/session-preview', false],
  ['/interviews/7/session', false],
  ['/interviews/7/review', true],
  ['/cases', true],
])('shows the appropriate application header at %s', async (pathname, hasHeader) => {
  session.user = {id: 1, role: 'superuser'};
  session.isLoading = false;
  render(<MemoryRouter initialEntries={[pathname]}><Routes>
    <Route element={<AppContainer />}><Route path="*" element={<h1>Page content</h1>} /></Route>
  </Routes></MemoryRouter>);
  await screen.findByRole('heading', {name: 'Page content'});
  expect(Boolean(screen.queryByRole('banner'))).toBe(hasHeader);
});

it.each(['student', 'teacher'])('allows %s recalibration for the same active interview during an authorized resume', async (role) => {
  session.user = {id: 1, role};
  session.isLoading = false;
  active.mockResolvedValue({id: 7, status: 'in_progress', startTime: '2026-11-08T12:00:00Z'});
  render(<MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {
    draftInterviewId: 7, resume: {resumeAttemptId: 'attempt', offsetMs: 60_000},
  }}]}><Routes><Route element={<AppContainer />}>
    <Route path="/interviews/calibration" element={<h1>Resume calibration</h1>} />
    <Route path="/interviews/7/session" element={<h1>Active interview</h1>} />
  </Route></Routes></MemoryRouter>);
  await screen.findByRole('heading', {name: 'Resume calibration'});
  expect(screen.queryByRole('heading', {name: 'Active interview'})).toBeNull();
});

it.each(['/cases', '/interviews/calibration'])('redirects a teacher with an active interview from %s before mounting another flow', async (pathname) => {
  session.user = {id: 1, role: 'teacher'};
  session.isLoading = false;
  active.mockResolvedValue({id: 7, status: 'in_progress', startTime: '2026-11-08T12:00:00Z'});
  const Other = vi.fn(() => <h1>Other flow</h1>);
  render(<MemoryRouter initialEntries={[pathname]}><Routes><Route element={<AppContainer />}>
    <Route path={pathname} element={<Other />} />
    <Route path="/interviews/7/session" element={<h1>Resume interview</h1>} />
  </Route></Routes></MemoryRouter>);
  await screen.findByRole('heading', {name: 'Resume interview'});
  expect(active).toHaveBeenCalled();
  expect(Other).not.toHaveBeenCalled();
  expect(screen.queryByRole('heading', {name: 'Other flow'})).toBeNull();
});

it('checks a new account before mounting its protected content', async () => {
  session.user = {id: 1, role: 'student'};
  session.isLoading = false;
  active.mockResolvedValue(null);
  const Protected = vi.fn(() => <h1>Protected account content</h1>);
  const routes = () => <MemoryRouter initialEntries={['/interviews']}><Routes>
    <Route element={<AppContainer />}><Route path="/interviews" element={<Protected />} /></Route>
  </Routes></MemoryRouter>;
  const view = render(routes());
  await screen.findByText('Protected account content');
  Protected.mockClear();
  let resolve!: (value: null) => void;
  active.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
  session.user = {id: 2, role: 'student'};
  view.rerender(routes());
  expect(Protected).not.toHaveBeenCalled();
  expect(screen.queryByText('Protected account content')).toBeNull();
  await act(async () => resolve(null));
  await screen.findByText('Protected account content');
});
