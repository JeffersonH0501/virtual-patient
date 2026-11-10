import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {MemoryRouter} from 'react-router-dom';
import type {PropsWithChildren} from 'react';
import {PatientPreview} from './PatientPreview';

vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {role: 'superuser', name: 'Preview user'}})}));
const media = vi.hoisted(() => ({startCamera: vi.fn(), startMicrophone: vi.fn(), stopAll: vi.fn(), cameraState: 'idle', microphoneState: 'idle'}));
vi.mock('../../contexts/interviewMedia', () => ({useInterviewMedia: () => media}));
vi.mock('../../hooks/useHandsFreeSpeech', () => ({useHandsFreeSpeech: () => ({isListening: false, audioLevel: 0, hasPendingUtterance: false, isSubmittingUtterance: false})}));
vi.mock('../common/Modal', () => ({Modal: ({open, children}: PropsWithChildren<{open: boolean}>) => open ? <div role="dialog">{children}</div> : null}));
vi.mock('../ClinicalChat/ClinicalHypotheses', () => ({ClinicalHypotheses: () => <p>Hypotheses</p>}));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

it('shows the timer beside the title and a centered end action inside the panel', () => {
  vi.useFakeTimers();
  vi.stubGlobal('ResizeObserver', class {
    observe = vi.fn();
    disconnect = vi.fn();
  });
  render(<MemoryRouter initialEntries={[{pathname: '/interviews/session-preview', state: {
    clinicalCaseId: 1, personalityId: 1, gender: 'female', patientResponseLanguage: 'es', patientName: 'Preview patient',
  }}]}><PatientPreview /></MemoryRouter>);
  expect(screen.getByRole('heading', {name: 'clinicalChat.call.interview'})).toBeTruthy();
  expect(screen.queryByText('Hola, mucho gusto.')).toBeNull();
  expect(screen.getByRole('dialog').textContent).toContain('clinicalChat.welcome.scope');
  expect(screen.getByRole('dialog').textContent).toContain('clinicalChat.welcome.duration');
  act(() => vi.advanceTimersByTime(30_000));
  const clock = screen.getByLabelText('clinicalChat.call.elapsedTime');
  expect(clock.textContent).toBe('0:00');
  expect(media.startCamera).not.toHaveBeenCalled();
  expect(media.startMicrophone).not.toHaveBeenCalled();
  expect(screen.getByRole('button', {name: 'clinicalChat.endInterview'}).hasAttribute('disabled')).toBe(true);
  fireEvent.click(screen.getByRole('button', {name: 'clinicalChat.welcome.accept'}));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.queryByText('Hola, mucho gusto.')).toBeNull();
  expect(screen.getByText('clinicalChat.call.patientThinking')).toBeTruthy();
  expect(media.startCamera).toHaveBeenCalledOnce();
  expect(media.startMicrophone).toHaveBeenCalledOnce();
  act(() => vi.advanceTimersByTime(2_000));
  expect(clock.textContent).toBe('0:02');
  expect(screen.queryByText('patientProfile.interviewSummary')).toBeNull();
  const conversation = screen.getByRole('region', {name: 'clinicalChat.call.interview'});
  const panel = conversation.closest('.ui-panel')!;
  const end = screen.getByRole('button', {name: 'clinicalChat.endInterview'});
  expect(panel.contains(end)).toBe(true);
  const footer = end.closest('footer')!;
  expect(footer.classList.contains('justify-center')).toBe(true);
  expect(footer.classList.contains('ui-panel-footer')).toBe(true);
  expect(conversation.compareDocumentPosition(footer)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  expect(screen.getByRole('heading', {name: 'clinicalChat.call.interview'}).closest('header')?.contains(screen.getByLabelText('clinicalChat.call.elapsedTime'))).toBe(true);
  fireEvent.click(end);
  expect(screen.getByRole('dialog').textContent).toContain('Hypotheses');
});
