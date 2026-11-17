/* eslint-disable max-classes-per-file */
import {cleanup, render, act, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {PropsWithChildren, StrictMode} from 'react';
import {ConversationTranscript} from './ConversationTranscript';
import {Message} from '../../types';
import {loadPatientSpeechBlob} from '../../services/speech/patientSpeechUrl';

vi.mock('../../services/speech/patientSpeechUrl', () => ({
  patientSpeechUrl: () => 'http://localhost:8000/medical-interviews/7/messages/12/speech',
  loadPatientSpeechBlob: vi.fn(),
}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('../common/Motion', () => ({
  MotionMessage: ({children}: PropsWithChildren) => <div>{children}</div>,
}));
vi.mock('../common/Motion/hooks', () => ({useAppMotion: () => ({reduced: true})}));
class Audio {
  static instances: Audio[] = [];
  ended = false;
  src = '';
  crossOrigin = '';
  onplaying?: () => void;
  onended?: () => void;
  onerror?: () => void;
  onwaiting?: () => void;
  onpause?: () => void;
  onseeking?: () => void;
  pause = vi.fn();
  removeAttribute = vi.fn();
  load = vi.fn();
  constructor() {
    Audio.instances.push(this);
  }
  play = vi.fn(async () => undefined);
}
const props = () => ({
  interviewId: 7,
  messages: [
    {
      id: 12,
      content: 'Synthetic patient',
      senderType: 'assistant',
      messageMetadata: {isNew: true},
    } as Message,
  ],
  isListening: false,
  audioLevel: 0,
  patientAudioLevel: 0,
  hasPendingUtterance: false,
  isSubmittingUtterance: false,
  onSubmitUtterance: vi.fn(),
  isLoading: false,
  audioAutoPlayEnabled: true,
  captureEnabled: true,
  routePatientAudio: () => true,
  onPatientSpeakingChange: vi.fn(),
  onPatientTurnStart: vi.fn(),
  onPatientTurnEnd: vi.fn(),
  onPatientTurnComplete: vi.fn(),
});
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(loadPatientSpeechBlob).mockResolvedValue('blob:patient-audio');
  Audio.instances = [];
  vi.stubGlobal('Audio', Audio);
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn();
      disconnect = vi.fn();
    },
  );
  vi.stubGlobal('requestAnimationFrame', vi.fn().mockReturnValue(1));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('sends pending audio with Enter without overriding focused controls or dialogs', () => {
  const callbacks = {...props(), messages: [], isListening: true};
  const {rerender} = render(<ConversationTranscript {...callbacks} />);
  fireEvent.keyDown(document.body, {key: 'Enter'});
  expect(callbacks.onSubmitUtterance).not.toHaveBeenCalled();
  expect(screen.getByText('clinicalChat.call.sendAudioHint')).toBeTruthy();

  rerender(<ConversationTranscript {...callbacks} hasPendingUtterance />);
  fireEvent.keyDown(document.body, {key: 'Enter'});
  fireEvent.keyDown(document.body, {key: 'Enter', repeat: true});
  fireEvent.keyDown(screen.getByLabelText('clinicalChat.call.sendAudio'), {key: 'Enter'});

  const dialog = document.createElement('div');
  dialog.setAttribute('data-modal-open', 'true');
  document.body.append(dialog);
  fireEvent.keyDown(document.body, {key: 'Enter'});
  dialog.remove();
  expect(callbacks.onSubmitUtterance).toHaveBeenCalledOnce();
  expect(screen.queryByText('clinicalChat.call.sendAudioHint')).toBeNull();
});

it('keeps the send instruction visible until the first enabled send click', () => {
  vi.useFakeTimers();
  const callbacks = {...props(), messages: [], isListening: true};
  const view = render(<ConversationTranscript {...callbacks} />);
  const button = screen.getByRole('button', {name: 'clinicalChat.call.sendAudio'});
  const hint = screen.getByText('clinicalChat.call.sendAudioHint');
  expect(button.getAttribute('aria-describedby')).toBe(hint.id);
  expect(hint.classList.contains('call-send-coachmark')).toBe(true);
  expect(button.classList.contains('call-send-audio--highlighted')).toBe(true);
  act(() => vi.advanceTimersByTime(30_000));
  view.rerender(<ConversationTranscript {...callbacks} audioLevel={.6} />);
  fireEvent.click(button);
  expect(callbacks.onSubmitUtterance).not.toHaveBeenCalled();
  expect(screen.getByText('clinicalChat.call.sendAudioHint')).toBeTruthy();
  view.rerender(<ConversationTranscript {...callbacks} isListening={false} />);
  expect(screen.getByText('clinicalChat.call.sendAudioHint')).toBeTruthy();
  view.rerender(<ConversationTranscript {...callbacks} hasPendingUtterance />);
  fireEvent.click(button);
  expect(callbacks.onSubmitUtterance).toHaveBeenCalledOnce();
  expect(screen.queryByText('clinicalChat.call.sendAudioHint')).toBeNull();
  expect(button.hasAttribute('aria-describedby')).toBe(false);
  expect(button.classList.contains('call-send-audio--highlighted')).toBe(false);
});

it('allows retrying the opening audio when browser autoplay fails', () => {
  const callbacks = props();
  render(<ConversationTranscript {...callbacks} />);
  act(() => Audio.instances[0].onerror?.());
  expect(screen.getByRole('alert')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'common.retry'}));
  expect(Audio.instances).toHaveLength(2);
  act(() => Audio.instances[1].onplaying?.());
  expect(callbacks.onPatientTurnStart).toHaveBeenCalledWith(12, 0, 'Synthetic patient');
});

it('preserves the student bubble when the server confirms its provisional message', () => {
  const callbacks = props();
  const student = {...callbacks.messages[0], id: 999, senderType: 'user', content: 'My question'} as Message;
  const {rerender} = render(<ConversationTranscript {...callbacks} messages={[student]} isLoading />);
  const bubble = screen.getByText('My question').parentElement;
  rerender(<ConversationTranscript {...callbacks} messages={[{...student, id: 42}, ...callbacks.messages]} />);
  expect(screen.getByText('My question').parentElement).toBe(bubble);
});

it('reactivates audio output before playing each patient response', async () => {
  const resume = vi.fn().mockResolvedValue(undefined);
  render(<ConversationTranscript {...props()} resumeAudioGraph={resume} />);
  await act(async () => {
 await Promise.resolve();
});

  expect(resume).toHaveBeenCalledOnce();
  expect(Audio.instances[0].play).toHaveBeenCalledOnce();
  expect(resume.mock.invocationCallOrder[0]).toBeLessThan(Audio.instances[0].play.mock.invocationCallOrder[0]);
});

it('keeps patient playback when the optional audio graph fails', async () => {
  const callbacks = {...props(), routePatientAudio: () => {
    throw new Error('Audio graph unavailable');
  }};
  render(<ConversationTranscript {...callbacks} resumeAudioGraph={() => Promise.reject(new Error('Audio context suspended'))} />);
  await waitFor(() => expect(Audio.instances[0].play).toHaveBeenCalledOnce());
  expect(screen.queryByText('clinicalChat.call.audioUnavailable')).toBeNull();
});

it('does not expire patient audio while synchronization intentionally pauses playback', async () => {
  vi.useFakeTimers();
  const callbacks = props();
  const {rerender} = render(<ConversationTranscript {...callbacks} />);
  await act(async () => {
 await Promise.resolve();
});
  rerender(<ConversationTranscript {...callbacks} capturePaused />);
  await act(async () => {
 await vi.advanceTimersByTimeAsync(25_000);
});
  expect(screen.queryByText('clinicalChat.call.audioUnavailable')).toBeNull();
  expect(Audio.instances[0].removeAttribute).not.toHaveBeenCalled();
  rerender(<ConversationTranscript {...callbacks} />);
  await act(async () => {
 await Promise.resolve();
});
  expect(Audio.instances[0].play).toHaveBeenCalledTimes(2);
});
it('keeps the patient turn locked without offering sound reactivation', async () => {
  const resume = vi.fn().mockResolvedValue(undefined);
  render(<ConversationTranscript {...props()} isListening resumeAudioGraph={resume} />);
  await act(async () => {
 await Promise.resolve();
});
  act(() => Audio.instances[0].onplaying?.());
  expect(screen.queryByText('clinicalChat.call.reactivateAudio')).toBeNull();
  expect(Audio.instances).toHaveLength(1);
  expect((screen.getByLabelText('clinicalChat.call.sendAudio') as HTMLButtonElement).disabled).toBe(true);
});

it('keeps the patient turn pending after audio failure and only offers a retry', () => {
  const callbacks = props();
  render(<ConversationTranscript {...callbacks} />);
  act(() => Audio.instances[0].onerror?.());
  expect(screen.getByRole('alert').textContent).toContain('clinicalChat.call.audioUnavailable');
  expect(screen.getByRole('button', {name: 'common.retry'})).toBeTruthy();
  expect(screen.queryByRole('button', {name: /continueWithoutPatientAudio/})).toBeNull();
  expect(callbacks.onPatientTurnComplete).not.toHaveBeenCalled();
});

it('retries policy-blocked audio directly on the already loaded player', async () => {
  const callbacks = props();
  const player = new Audio();
  player.play.mockRejectedValueOnce(new DOMException('Gesture required', 'NotAllowedError'));
  const revoke = vi.fn();
  vi.stubGlobal('URL', {revokeObjectURL: revoke});
  vi.mocked(loadPatientSpeechBlob).mockResolvedValue('blob:greeting');
  const view = render(<ConversationTranscript {...callbacks} preparedAudio={player as unknown as HTMLAudioElement} />);
  const retry = await screen.findByRole('button', {name: 'clinicalChat.call.playPatientAudio'});
  expect(loadPatientSpeechBlob).toHaveBeenCalledOnce();
  expect(callbacks.onPatientTurnComplete).not.toHaveBeenCalled();
  fireEvent.click(retry);
  expect(player.play).toHaveBeenCalledTimes(2);
  expect(loadPatientSpeechBlob).toHaveBeenCalledOnce();
  act(() => player.onplaying?.());
  expect(callbacks.onPatientTurnStart).toHaveBeenCalledWith(12, 0, 'Synthetic patient');
  view.unmount();
  expect(revoke).toHaveBeenCalledWith('blob:greeting');
});

it('does not show the send instruction when the interview already has student messages', () => {
  const callbacks = props();
  render(<ConversationTranscript {...callbacks} messages={[{...callbacks.messages[0], senderType: 'user'} as Message]} />);
  expect(screen.queryByText('clinicalChat.call.sendAudioHint')).toBeNull();
});

it('keeps the student turn on screen until its transcript arrives, then waits for the patient', () => {
  const callbacks = {...props(), messages: [], isSubmittingUtterance: true};
  const {rerender} = render(<ConversationTranscript {...callbacks} />);
  const send = screen.getByLabelText('clinicalChat.call.sendAudio');
  expect(send.closest('.transcript-status')?.hasAttribute('hidden')).toBe(false);
  expect(send.querySelector('.animate-spin, [class*="animate-spin"]')).not.toBeNull();
  expect(screen.getByText('clinicalChat.call.patientThinking').closest('[hidden]')).not.toBeNull();

  const transcript = {id: 30, content: 'Synthetic question', senderType: 'user', createdAt: '', interviewId: 1} as Message;
  rerender(<ConversationTranscript {...callbacks} messages={[transcript]} isLoading />);
  expect(send.closest('.transcript-status')?.hasAttribute('hidden')).toBe(true);
  expect(screen.getByText('Synthetic question')).toBeTruthy();
  expect(screen.getByRole('status').textContent).toContain('clinicalChat.call.patientThinking');
});

it('distinguishes preparing patient audio from actual playback', async () => {
  const callbacks = props();
  const current = callbacks.messages[0];
  render(<ConversationTranscript {...callbacks}
    messages={[{...current, id: 11, content: 'Earlier patient response'}, current]} />);
  expect(screen.getByText('Earlier patient response')).toBeTruthy();
  expect(screen.queryByText(current.content)).toBeNull();
  // The reply shows the patient audio indicator (heads-up while loading, live wave when playing), never plain text.
  await waitFor(() => expect(document.querySelector('[data-speaker="patient"]')).not.toBeNull());
  const audio = Audio.instances[0];
  act(() => audio.onplaying?.());
  expect(document.querySelector('.transcript-voice-bubble--pending')).toBeNull();
  expect(document.querySelector('[data-speaker="patient"]')).not.toBeNull();
  expect(screen.queryByText(current.content)).toBeNull();
  act(() => {
    audio.ended = true;
    audio.onended?.();
  });
  expect(screen.getByText(current.content)).toBeTruthy();
});

it('shows the queued greeting as preparation and waits for capture before requesting audio', () => {
  const callbacks = props();
  const {rerender} = render(<ConversationTranscript {...callbacks} playbackReady={false} />);
  expect(Audio.instances).toHaveLength(0);
  expect(screen.queryByText(callbacks.messages[0].content)).toBeNull();
  expect(screen.getByText('clinicalChat.call.patientThinking')).toBeTruthy();
  expect(document.querySelector('[data-speaker="patient"]')).toBeNull();
  rerender(<ConversationTranscript {...callbacks} playbackReady />);
  rerender(<ConversationTranscript {...callbacks} playbackReady />);
  expect(Audio.instances).toHaveLength(1);
  expect(callbacks.onPatientTurnStart).not.toHaveBeenCalled();
  act(() => Audio.instances[0].onplaying?.());
  expect(callbacks.onPatientTurnStart).toHaveBeenCalledOnce();
});

it('loads patient audio through the authenticated fetch without capture', async () => {
  const callbacks = {...props(), captureEnabled: false};
  render(<ConversationTranscript {...callbacks} playbackReady={false} />);
  await waitFor(() => expect(loadPatientSpeechBlob).toHaveBeenCalledOnce());
  expect(Audio.instances).toHaveLength(1);
  expect(Audio.instances[0].src).toBe('blob:patient-audio');
});

it('cancels the fetched audio and ignores late playback after unmount', async () => {
  const callbacks = props();
  const {unmount} = render(<ConversationTranscript {...callbacks} />);
  await waitFor(() => expect(Audio.instances).toHaveLength(1));
  const audio = Audio.instances[0];
  expect(audio.src).toBe('blob:patient-audio');
  expect(callbacks.onPatientTurnStart).not.toHaveBeenCalled();
  unmount();
  expect(audio.removeAttribute).toHaveBeenCalledWith('src');
  expect(audio.load).toHaveBeenCalledOnce();
  act(() => audio.onplaying?.());
  expect(callbacks.onPatientTurnStart).not.toHaveBeenCalled();
});

it('ignores a late TTS failure after leaving the interview', () => {
  const callbacks = props();
  const {unmount} = render(<ConversationTranscript {...callbacks} />);
  const audio = Audio.instances[0];
  unmount();
  callbacks.onPatientTurnComplete.mockClear();
  act(() => audio.onerror?.());
  expect(callbacks.onPatientTurnComplete).not.toHaveBeenCalled();
});

it('preserves actual playback completion and its message association', () => {
  const callbacks = props();
  render(<ConversationTranscript {...callbacks} />);
  const audio = Audio.instances[0];
  act(() => {
    audio.onplaying?.();
    audio.onplaying?.();
  });
  expect(callbacks.onPatientTurnStart).toHaveBeenCalledExactlyOnceWith(12, 0, 'Synthetic patient');
  act(() => {
    audio.ended = true;
    audio.onended?.();
  });
  expect(callbacks.onPatientTurnEnd).toHaveBeenCalledWith(12, true);
  expect(callbacks.onPatientTurnComplete).toHaveBeenCalledOnce();
});

it('does not report an audio error when releasing the completed player', () => {
  const callbacks = props();
  render(<ConversationTranscript {...callbacks} />);
  const audio = Audio.instances[0];
  audio.load.mockImplementation(() => audio.onerror?.());
  act(() => {
    audio.onplaying?.();
    audio.ended = true;
    audio.onended?.();
  });
  expect(screen.queryByRole('alert')).toBeNull();
  expect(callbacks.onPatientTurnComplete).toHaveBeenCalledOnce();
});

it('treats a buffering stall as continuous when playback still reaches its end', () => {
  // iOS Safari fires `waiting` during normal streamed playback; it must not mark
  // the completed turn interrupted, which would discard its playback timing window.
  const callbacks = props();
  render(<ConversationTranscript {...callbacks} />);
  const audio = Audio.instances[0];
  act(() => {
    audio.onplaying?.();
    audio.onwaiting?.();
    audio.ended = true;
    audio.onended?.();
  });
  expect(callbacks.onPatientTurnEnd).toHaveBeenCalledWith(12, true);
});

it('marks playback interrupted when the user pauses it before the end', () => {
  const callbacks = props();
  render(<ConversationTranscript {...callbacks} />);
  const audio = Audio.instances[0];
  act(() => {
    audio.onplaying?.();
    audio.onpause?.();
    audio.ended = true;
    audio.onended?.();
  });
  expect(callbacks.onPatientTurnEnd).toHaveBeenCalledWith(12, true, false);
});

it('plays the current message once after StrictMode effect cleanup and setup', () => {
  const callbacks = props();
  render(
    <StrictMode>
      <ConversationTranscript {...callbacks} />
    </StrictMode>,
  );
  act(() => Audio.instances.forEach((audio) => audio.onplaying?.()));
  expect(callbacks.onPatientTurnStart).toHaveBeenCalledOnce();
});

it('shows the thinking indicator only while the reply is still being generated', () => {
  const callbacks = props();
  // With no reply yet and generation in flight, the "thinking" indicator is the only status.
  render(<ConversationTranscript {...callbacks} messages={[]} isLoading />);
  expect(screen.getByRole('status').textContent).toBe('clinicalChat.call.patientThinking');
  // The heads-up and live-wave stages once a reply exists are covered by
  // "distinguishes preparing patient audio from actual playback".
});

it('does not expose an actionable student wave while capture is paused', () => {
  render(<ConversationTranscript {...props()} messages={[]} isListening hasPendingUtterance capturePaused />);
  expect(screen.queryByRole('button', {name: 'clinicalChat.call.sendAudio'})).toBeNull();
});

it('shows bubble times from the interview clock and none until a time is known', () => {
  const callbacks = props();
  const question = {id: 40, content: 'Clock question', senderType: 'user', createdAt: '2026-11-13T15:00:00Z', interviewId: 1} as Message;
  const later = {id: 41, content: 'Untimed question', senderType: 'user', createdAt: '2026-11-13T15:09:00Z', interviewId: 1} as Message;
  render(<ConversationTranscript {...callbacks} messages={[question, later]} messageTimes={{40: 33_400}} />);
  expect(screen.getByText('Clock question').parentElement?.textContent).toContain('0:33');
  expect(screen.getByText('Untimed question').parentElement?.querySelector('.recap-turn-meta')).toBeNull();
});
