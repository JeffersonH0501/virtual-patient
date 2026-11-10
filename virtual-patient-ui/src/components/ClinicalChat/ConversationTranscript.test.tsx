/* eslint-disable max-classes-per-file */
import {cleanup, render, act, fireEvent, screen} from '@testing-library/react';
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

it('keeps the patient turn pending after audio failure until explicitly choosing the written reply', () => {
  const callbacks = props();
  render(<ConversationTranscript {...callbacks} />);
  act(() => Audio.instances[0].onerror?.());
  expect(callbacks.onPatientTurnComplete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'clinicalChat.call.continueWithoutPatientAudio'}));
  expect(callbacks.onPatientTurnComplete).toHaveBeenCalledExactlyOnceWith(12, 'written');
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

it('collapses the send indicator once the patient starts preparing a response', () => {
  const callbacks = {...props(), messages: [], isSubmittingUtterance: true};
  const {rerender} = render(<ConversationTranscript {...callbacks} />);
  const send = screen.getByLabelText('clinicalChat.call.sendAudio');
  expect(send.closest('[inert]')).toBeNull();

  rerender(<ConversationTranscript {...callbacks} isLoading />);
  expect(send.closest('[inert]')?.hasAttribute('hidden')).toBe(true);
  expect(screen.getByText('clinicalChat.call.patientThinking').closest('[aria-hidden]')).toBeNull();
});

it('distinguishes preparing patient audio from actual playback', () => {
  const callbacks = props();
  const current = callbacks.messages[0];
  render(<ConversationTranscript {...callbacks}
    messages={[{...current, id: 11, content: 'Earlier patient response'}, current]} />);
  expect(screen.getByText('Earlier patient response')).toBeTruthy();
  expect(screen.queryByText(current.content)).toBeNull();
  expect(document.querySelector('[data-speaker="patient"]')).toBeNull();
  expect(screen.getByText('clinicalChat.call.patientThinking')).toBeTruthy();
  const audio = Audio.instances[0];
  act(() => audio.onplaying?.());
  expect(screen.queryByRole('status')).toBeNull();
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

it('cancels the native download and ignores late playback after unmount', () => {
  const callbacks = props();
  const {unmount} = render(<ConversationTranscript {...callbacks} />);
  const audio = Audio.instances[0];
  expect(audio.src).toContain('/medical-interviews/7/messages/12/speech');
  expect(audio.crossOrigin).toBe('use-credentials');
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

it('keeps one waiting indicator across response generation and audio loading until actual playback', () => {
  const callbacks = props();
  const {rerender} = render(<ConversationTranscript {...callbacks} messages={[]} isLoading />);
  expect(screen.getAllByRole('status')).toHaveLength(1);
  const waiting = screen.getByRole('status');
  expect(waiting.textContent).toBe('clinicalChat.call.patientThinking');
  rerender(<ConversationTranscript {...callbacks} isLoading={false} />);
  expect(screen.getAllByRole('status')).toHaveLength(1);
  expect(screen.getByRole('status')).toBe(waiting);
  expect(document.querySelector('[data-speaker="patient"]')).toBeNull();
  act(() => Audio.instances[0].onplaying?.());
  expect(screen.queryByRole('status')).toBeNull();
  expect(document.querySelector('[data-speaker="patient"]')).toBeTruthy();
});

it('does not expose an actionable student wave while capture is paused', () => {
  render(<ConversationTranscript {...props()} messages={[]} isListening hasPendingUtterance capturePaused />);
  expect(screen.queryByRole('button', {name: 'clinicalChat.call.sendAudio'})).toBeNull();
});
