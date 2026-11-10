import {afterEach, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {BlockInterviewRecap} from './BlockInterviewRecap';
import type {InterviewRecap} from '../../types/recording';

vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {role: 'student'}})}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('../../services/recordings', () => ({resolveRecordingSource: (source?: string | null) => source}));
afterEach(() => {
  cleanup(); vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const replay = (): InterviewRecap => ({interviewId: 7, recordingStatus: 'ready', durationMs: 4000,
  blocks: [{blockId: 'one', offsetMs: 0, durationMs: 4000, studentVideoSource: '/original.webm', patientAudioSource: '/exact.mp3',
    metadata: {studentMessageId: 1, patientMessageId: 2, studentSpeech: {startMs: 0, endMs: 600}, patientPlayback: {startMs: 1400, endMs: 3800}}}],
  turns: [{turnId: 'patient', messageId: 2, speaker: 'patient', transcript: 'Patient speech', startMs: 1400, endMs: 3800,
    inputSource: 'tts', timingSource: 'tts_playback', timingQuality: 'measured'}]});

const mediaPlayback = () => {
  const active = new WeakSet<HTMLMediaElement>();
  vi.spyOn(HTMLMediaElement.prototype, 'paused', 'get').mockImplementation(function () { return !active.has(this); });
  const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(async function () { active.add(this); });
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(function () { active.delete(this); });
  return play;
};

it('keeps playback active after seeking to the current position', async () => {
  mediaPlayback();
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  const {container} = render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  const video = container.querySelector('video')!;
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  expect(video.paused).toBe(false);
  fireEvent.change(screen.getByLabelText('clinicalChat.recap.timeline'), {target: {value: '0'}});
  expect(video.paused).toBe(false);
});

it('prepares the next video before the current block ends and reuses it across the boundary', async () => {
  mediaPlayback();
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  let tick!: FrameRequestCallback;
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback) => { tick = callback; return 1; }));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const data = replay();
  data.durationMs = 8000;
  data.blocks!.push({...data.blocks![0], blockId: 'two', offsetMs: 4000, studentVideoSource: '/next.webm'});
  const {container} = render(<BlockInterviewRecap recap={data} infoDisabled={false} />);
  const next = [...container.querySelectorAll('video')].find((item) => item.getAttribute('src') === '/next.webm');
  expect(next).toBeDefined();
  const current = [...container.querySelectorAll('video')].find((item) => item.getAttribute('src') === '/original.webm')!;
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  current.currentTime = 4;
  vi.spyOn(current, 'ended', 'get').mockReturnValue(true);
  act(() => tick(100));
  expect([...container.querySelectorAll('video')].find((item) => item.getAttribute('src') === '/next.webm')).toBe(next);
  expect(next?.className).not.toContain('hidden');
});

it('stops with a recoverable error when the next block has no playable media', async () => {
  mediaPlayback();
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  let tick!: FrameRequestCallback;
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback) => { tick = callback; return 1; }));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const data = replay();
  data.durationMs = 8000;
  data.blocks!.push({...data.blocks![0], blockId: 'missing', offsetMs: 4000, studentVideoSource: null, patientAudioSource: null});
  const {container} = render(<BlockInterviewRecap recap={data} infoDisabled={false} />);
  const current = container.querySelector('video')!;
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  current.currentTime = 4;
  vi.spyOn(current, 'ended', 'get').mockReturnValue(true);
  act(() => tick(100));
  expect(screen.getByRole('alert')).toBeDefined();
  expect(screen.getByLabelText('clinicalChat.recap.play')).toBeDefined();
  expect((screen.getByLabelText('clinicalChat.recap.timeline') as HTMLInputElement).value).toBe('4');
});

it('surfaces a next-video preload failure when that block becomes active', async () => {
  mediaPlayback();
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  let tick!: FrameRequestCallback;
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback) => { tick = callback; return 1; }));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const data = replay();
  data.durationMs = 8000;
  data.blocks!.push({...data.blocks![0], blockId: 'two', offsetMs: 4000, studentVideoSource: '/next.webm'});
  const {container} = render(<BlockInterviewRecap recap={data} infoDisabled={false} />);
  const [current, next] = container.querySelectorAll('video');
  Object.defineProperty(next, 'error', {configurable: true, value: {code: 4}});
  fireEvent.error(next);
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  current.currentTime = 4;
  vi.spyOn(current, 'ended', 'get').mockReturnValue(true);
  act(() => tick(100));
  expect(screen.getByRole('alert')).toBeDefined();
  expect(screen.getByLabelText('clinicalChat.recap.play')).toBeDefined();
  const reload = vi.spyOn(next, 'load').mockImplementation(() => undefined);
  fireEvent.click(screen.getByLabelText('clinicalChat.recap.play'));
  expect(reload).toHaveBeenCalledOnce();
});

it('does not advance past media that ends before the confirmed block boundary', async () => {
  mediaPlayback();
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  let tick!: FrameRequestCallback;
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback) => { tick = callback; return 1; }));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const {container} = render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  const video = container.querySelector('video')!;
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  video.currentTime = 2;
  Object.defineProperty(video, 'duration', {configurable: true, value: 2});
  vi.spyOn(video, 'ended', 'get').mockReturnValue(true);
  act(() => tick(100));
  expect((screen.getByLabelText('clinicalChat.recap.timeline') as HTMLInputElement).value).toBe('2');
  expect(screen.getByRole('alert')).toBeDefined();
});

it('accepts a normal final video frame when the browser reports the complete media duration', async () => {
  mediaPlayback();
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  let tick!: FrameRequestCallback;
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback) => { tick = callback; return 1; }));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const {container} = render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  const video = container.querySelector('video')!;
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  video.currentTime = 3.8;
  Object.defineProperty(video, 'duration', {configurable: true, value: 4});
  vi.spyOn(video, 'ended', 'get').mockReturnValue(true);
  act(() => tick(100));
  expect(screen.queryByRole('alert')).toBeNull();
  expect((screen.getByLabelText('clinicalChat.recap.timeline') as HTMLInputElement).value).toBe('4');
});

it('does not infer a truncated recording when the browser cannot report its duration', async () => {
  mediaPlayback();
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  let tick!: FrameRequestCallback;
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback) => { tick = callback; return 1; }));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const {container} = render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  const video = container.querySelector('video')!;
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  video.currentTime = 3.8;
  Object.defineProperty(video, 'duration', {configurable: true, value: Infinity});
  vi.spyOn(video, 'ended', 'get').mockReturnValue(true);
  act(() => tick(100));
  expect(screen.queryByRole('alert')).toBeNull();
  expect((screen.getByLabelText('clinicalChat.recap.timeline') as HTMLInputElement).value).toBe('4');
});

it('aligns patient audio before resuming after a seek while its media is loading', async () => {
  const play = mediaPlayback();
  const {container} = render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  const video = container.querySelector('video')!;
  const audio = container.querySelector('audio')!;
  vi.spyOn(video, 'readyState', 'get').mockReturnValue(2);
  const audioReady = vi.spyOn(audio, 'readyState', 'get').mockReturnValue(0);
  fireEvent.change(screen.getByLabelText('clinicalChat.recap.timeline'), {target: {value: '2.4'}});
  fireEvent.click(screen.getByLabelText('clinicalChat.recap.play'));
  await act(async () => undefined);
  play.mockClear();
  const starts: number[] = [];
  play.mockImplementation(async function () { if (this === audio) starts.push(this.currentTime); });
  audioReady.mockReturnValue(2);
  await act(async () => { fireEvent.canPlay(audio); });
  expect(starts.length).toBeGreaterThan(0);
  expect(starts.every((time) => Math.abs(time - 1) < .01)).toBe(true);
});

it('freezes the master clock when video buffers even before readyState changes', async () => {
  mediaPlayback();
  let tick!: FrameRequestCallback;
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback) => { tick = callback; return 1; }));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const {container} = render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  const video = container.querySelector('video')!;
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  fireEvent.change(screen.getByLabelText('clinicalChat.recap.timeline'), {target: {value: '2.4'}});
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  fireEvent.waiting(video);
  video.currentTime = 2.8;
  act(() => tick(100));
  expect(Number((screen.getByLabelText('clinicalChat.recap.timeline') as HTMLInputElement).value)).toBe(2.4);
});

it('does not invent playback time for a block whose media is unavailable', async () => {
  mediaPlayback();
  let tick!: FrameRequestCallback;
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback) => { tick = callback; return 1; }));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const data = replay();
  data.blocks![0].studentVideoSource = null;
  data.blocks![0].patientAudioSource = null;
  render(<BlockInterviewRecap recap={data} infoDisabled={false} />);
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  act(() => tick?.(performance.now() + 100));
  expect((screen.getByLabelText('clinicalChat.recap.timeline') as HTMLInputElement).value).toBe('0');
  expect(screen.getByRole('alert')).toBeDefined();
});

it('does not report an audio error for an absent patient source', () => {
  mediaPlayback();
  const data = replay();
  data.blocks![0].patientAudioSource = null;
  const {container} = render(<BlockInterviewRecap recap={data} patientName="Mario" infoDisabled={false} />);
  fireEvent.error(container.querySelector('audio')!);
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByText('Mario')).toBeDefined();
  expect(screen.getByText('Mario').className).not.toContain('bg-black');
  expect(screen.getByLabelText('clinicalChat.recap.volume').className).not.toContain('opacity-0');
});

it('ignores an interrupted play request when media is paused for buffering', async () => {
  const play = mediaPlayback();
  const {container} = render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  let reject!: (reason: unknown) => void;
  play.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }));
  fireEvent.click(screen.getByLabelText('clinicalChat.recap.play'));
  fireEvent.waiting(container.querySelector('video')!);
  await act(async () => reject(new DOMException('Playback was interrupted', 'AbortError')));
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByLabelText('clinicalChat.recap.pause')).toBeDefined();
});

it('ignores a stale playback rejection after rewinding to the beginning', async () => {
  const play = mediaPlayback();
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  let reject!: (reason: unknown) => void;
  play.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }));
  render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  fireEvent.change(screen.getByLabelText('clinicalChat.recap.timeline'), {target: {value: '2.4'}});
  fireEvent.click(screen.getByLabelText('clinicalChat.recap.play'));
  fireEvent.change(screen.getByLabelText('clinicalChat.recap.timeline'), {target: {value: '0'}});
  await act(async () => reject(new Error('Playback request superseded')));
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByLabelText('clinicalChat.recap.pause')).toBeDefined();
});

it('restarts from the first block when the final block has no media', async () => {
  mediaPlayback();
  const data = replay();
  data.durationMs = 8000;
  data.blocks!.push({...data.blocks![0], blockId: 'last', offsetMs: 4000, studentVideoSource: null, patientAudioSource: null});
  const {container} = render(<BlockInterviewRecap recap={data} infoDisabled={false} />);
  fireEvent.change(screen.getByLabelText('clinicalChat.recap.timeline'), {target: {value: '8'}});
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  expect(screen.queryByRole('alert')).toBeNull();
  expect((screen.getByLabelText('clinicalChat.recap.timeline') as HTMLInputElement).value).toBe('0');
  expect(container.querySelector('video')?.getAttribute('src')).toBe('/original.webm');
});

it('keeps the current audio source stable when preloading completes during playback', async () => {
  mediaPlayback();
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  const create = vi.fn().mockReturnValue('blob:patient');
  vi.stubGlobal('URL', Object.assign(class extends URL {}, {createObjectURL: create, revokeObjectURL: vi.fn()}));
  let resolve!: (value: unknown) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise((done) => { resolve = done; })));
  const {container} = render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  const audio = container.querySelector('audio')!;
  fireEvent.change(screen.getByLabelText('clinicalChat.recap.timeline'), {target: {value: '2.4'}});
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  await act(async () => resolve({ok: true, blob: async () => new Blob(['audio'], {type: 'audio/mpeg'})}));
  expect(audio.getAttribute('src')).toBe('/exact.mp3');
  expect(screen.queryByRole('alert')).toBeNull();
  fireEvent.click(screen.getByLabelText('clinicalChat.recap.pause'));
  expect(audio.getAttribute('src')).toBe('blob:patient');
});

it('preloads only current and next patient audio, then releases older blobs', async () => {
  mediaPlayback();
  const create = vi.fn().mockReturnValue('blob:patient');
  const revoke = vi.fn();
  vi.stubGlobal('URL', Object.assign(class extends URL {}, {createObjectURL: create, revokeObjectURL: revoke}));
  const request = vi.fn().mockResolvedValue({ok: true, blob: async () => new Blob(['audio'], {type: 'audio/mpeg'})});
  vi.stubGlobal('fetch', request);
  const data = replay();
  data.blocks!.push({...data.blocks![0], blockId: 'two', offsetMs: 4000, patientAudioSource: '/other.mp3'});
  data.blocks!.push({...data.blocks![0], blockId: 'three', offsetMs: 8000, patientAudioSource: '/third.mp3'});
  data.durationMs = 12000;
  const view = render(<BlockInterviewRecap recap={data} infoDisabled={false} />);
  await act(async () => undefined);
  expect(request).toHaveBeenCalledTimes(2);
  expect(request).toHaveBeenCalledWith('/exact.mp3', expect.objectContaining({credentials: 'include'}));
  expect(create).toHaveBeenCalledTimes(2);
  await act(async () => { fireEvent.change(screen.getByLabelText('clinicalChat.recap.timeline'), {target: {value: '4'}}); });
  expect(request).toHaveBeenCalledTimes(3);
  expect(request).toHaveBeenCalledWith('/third.mp3', expect.objectContaining({credentials: 'include'}));
  expect(revoke).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(revoke).toHaveBeenCalledTimes(3);
});

it('stops on a rejected play request and allows retry without losing the selected time', async () => {
  const play = mediaPlayback();
  const {container} = render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  fireEvent.change(screen.getByLabelText('clinicalChat.recap.timeline'), {target: {value: '2.4'}});
  play.mockRejectedValue(new Error('Playback blocked'));
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  expect(screen.getByRole('alert')).toBeDefined();
  expect(container.querySelector('video')!.paused).toBe(true);
  play.mockResolvedValue(undefined);
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  expect(screen.queryByRole('alert')).toBeNull();
  expect((screen.getByLabelText('clinicalChat.recap.timeline') as HTMLInputElement).value).toBe('2.4');
  expect(container.querySelector('audio')!.currentTime).toBeCloseTo(1);
});

it('resumes aligned media after the browser completes a seek', async () => {
  const play = mediaPlayback();
  const {container} = render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  const video = container.querySelector('video')!;
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2);
  const seeking = vi.spyOn(video, 'seeking', 'get').mockReturnValue(true);
  fireEvent.change(screen.getByLabelText('clinicalChat.recap.timeline'), {target: {value: '2.4'}});
  await act(async () => { fireEvent.click(screen.getByLabelText('clinicalChat.recap.play')); });
  play.mockClear();
  seeking.mockReturnValue(false);
  await act(async () => { fireEvent.seeked(video); });
  expect(play).toHaveBeenCalled();
  expect(container.querySelector('audio')!.currentTime).toBeCloseTo(1);
});

it('resets the replay clock on interview identity changes but preserves it on ordinary refresh', () => {
  mediaPlayback();
  const {rerender} = render(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  fireEvent.change(screen.getByLabelText('clinicalChat.recap.timeline'), {target: {value: '2.4'}});
  rerender(<BlockInterviewRecap recap={replay()} infoDisabled={false} />);
  expect((screen.getByLabelText('clinicalChat.recap.timeline') as HTMLInputElement).value).toBe('2.4');
  rerender(<BlockInterviewRecap recap={{...replay(), interviewId: 8}} infoDisabled={false} />);
  expect((screen.getByLabelText('clinicalChat.recap.timeline') as HTMLInputElement).value).toBe('0');
});

it('uses the original video and exact TTS with local offsets and mutes microphone playback during the patient', () => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  const recap: InterviewRecap = {interviewId: 1, recordingStatus: 'ready', durationMs: 4000, blocks: [0, 1].map((index) => ({
    blockId: String(index), offsetMs: index * 2000, durationMs: 2000, studentVideoSource: `/original-${index}.webm`, patientAudioSource: `/exact-${index}.mp3`,
    metadata: {studentMessageId: index * 2 + 1, patientMessageId: index * 2 + 2,
      studentSpeech: {startMs: 100, endMs: 600}, patientPlayback: {startMs: 1400, endMs: 1800}},
  })), turns: [{turnId: 'student', messageId: 1, speaker: 'student', transcript: 'Student speech', startMs: 100, endMs: 600,
    inputSource: 'microphone', timingSource: 'block_speech', timingQuality: 'measured'},
  {turnId: 'patient', messageId: 4, speaker: 'patient', transcript: 'Patient speech', startMs: 3400, endMs: 3800,
    inputSource: 'tts', timingSource: 'tts_playback', timingQuality: 'measured'}]};
  const {container} = render(<BlockInterviewRecap recap={recap} infoDisabled={false} />);
  let video = container.querySelector('video')!;
  fireEvent.click(screen.getByText('Student speech'));
  expect(video.getAttribute('src')).toBe('/original-0.webm');
  expect(video.muted).toBe(false);
  fireEvent.click(screen.getByText('Patient speech'));
  expect(video.isConnected).toBe(false);
  video = container.querySelector('video')!;
  expect(video.getAttribute('src')).toBe('/original-1.webm');
  expect(video.currentTime).toBeCloseTo(1.4);
  expect(video.muted).toBe(true);
  expect(container.querySelector('audio')?.getAttribute('src')).toBe('/exact-1.mp3');
  const volume = screen.getByLabelText('clinicalChat.recap.volume');
  fireEvent.change(volume, {target: {value: '.4'}});
  expect(video.volume).toBe(.4);
});
