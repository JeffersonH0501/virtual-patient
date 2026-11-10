import {afterEach, expect, it, vi} from 'vitest';
import {InterviewBlockRecorder} from './InterviewBlockRecorder';
import {type BlockMetadata, type InterviewBlockStore, type LocalInterviewBlock} from './InterviewBlockStore';

class Recorder extends EventTarget {
  static isTypeSupported = () => true;
  state = 'inactive';
  static current: Recorder;
  constructor() {
    super(); Recorder.current = this;
  }
  start() {
    this.state = 'recording'; this.dispatchEvent(new Event('start'));
  }
  pause() {
    this.state = 'paused';
  }
  resume() {
    this.state = 'recording';
  }
  chunk() {
    this.dispatchEvent(Object.assign(new Event('dataavailable'), {data: new Blob(['original'])}));
  }
  stop() {
    this.chunk(); this.state = 'inactive'; this.dispatchEvent(new Event('stop'));
  }
}

afterEach(() => {
  vi.unstubAllGlobals(); vi.restoreAllMocks();
});

it('keeps a single recorder through patient playback and commits final delivered bytes before closing', async () => {
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('MediaStream', vi.fn(function () {
    return {};
  }));
  let now = 100;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const block = {id: 'block', state: 'capturing', chunks: 0, metadata: {}} as LocalInterviewBlock;
  const store = {create: vi.fn(), put: vi.fn(), patch: vi.fn(async (_id: string, patch: Partial<LocalInterviewBlock>) => Object.assign(block, patch)), append: vi.fn(async (item: LocalInterviewBlock) => {
    item.chunks++;
  })};
  const onFailure = vi.fn();
  const recording = new InterviewBlockRecorder(store as unknown as InterviewBlockStore, block, onFailure);
  await recording.start({getVideoTracks: () => [{kind: 'video'}]} as unknown as MediaStream,
    {getAudioTracks: () => [{kind: 'audio'}]} as unknown as MediaStream);
  now = 1000;
  Recorder.current.chunk();
  await recording.checkpoint({student_speech: {start_ms: 100, end_ms: 800}});
  now = 2100;
  const final = await recording.close({patient_message_id: 2, duration_ms: 2000} as BlockMetadata);
  expect(final.chunks).toBe(2);
  expect(final.state).toBe('closed');
  expect(final.metadata.duration_ms).toBe(2000);
  expect(store.append).toHaveBeenCalledTimes(2);
  expect(onFailure).not.toHaveBeenCalled();
});

it('pauses on a local persistence failure and never publishes a closed original', async () => {
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('MediaStream', vi.fn(function () {
    return {};
  }));
  const block = {id: 'block', state: 'capturing', chunks: 0, metadata: {}} as LocalInterviewBlock;
  const store = {create: vi.fn(), put: vi.fn(), patch: vi.fn(), append: vi.fn().mockRejectedValue(new Error('Synthetic full storage'))};
  const onFailure = vi.fn();
  const recording = new InterviewBlockRecorder(store as unknown as InterviewBlockStore, block, onFailure);
  await recording.start({getVideoTracks: () => [{kind: 'video'}]} as unknown as MediaStream,
    {getAudioTracks: () => [{kind: 'audio'}]} as unknown as MediaStream);
  Recorder.current.chunk();
  await vi.waitFor(() => expect(onFailure).toHaveBeenCalledTimes(1));
  expect(Recorder.current.state).toBe('paused');
  await expect(recording.close({} as BlockMetadata)).rejects.toThrow('Synthetic full storage');
  expect(block.state).toBe('capturing');
});

it('excludes seventeen paused minutes from one minute of active recording', async () => {
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('MediaStream', vi.fn(function () {
    return {};
  }));
  let now = 100;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const block = {id: 'block', state: 'capturing', chunks: 0, metadata: {}} as LocalInterviewBlock;
  const store = {create: vi.fn(), patch: vi.fn(async (_id: string, patch: Partial<LocalInterviewBlock>) => Object.assign(block, patch)),
    append: vi.fn(async (item: LocalInterviewBlock) => {
      item.chunks++;
    })};
  const recording = new InterviewBlockRecorder(store as unknown as InterviewBlockStore, block, vi.fn());
  await recording.start({getVideoTracks: () => [{kind: 'video'}]} as unknown as MediaStream, {getAudioTracks: () => [{kind: 'audio'}]} as unknown as MediaStream);
  now += 60_000;
  recording.pause();
  now += 17 * 60_000;
  expect(recording.elapsed()).toBe(60_000);
  recording.resume();
  const closed = await recording.close({patient_message_id: 1} as BlockMetadata);
  expect(closed.metadata.duration_ms).toBe(60_000);
});

it('keeps historical speech timestamps unchanged after a later network pause', async () => {
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('MediaStream', vi.fn(function () { return {}; }));
  let now = 100;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const block = {id: 'block', state: 'capturing', chunks: 0, metadata: {}} as LocalInterviewBlock;
  const store = {create: vi.fn(), patch: vi.fn(), append: vi.fn()};
  const recording = new InterviewBlockRecorder(store as unknown as InterviewBlockStore, block, vi.fn());
  await recording.start({getVideoTracks: () => [{kind: 'video'}]} as unknown as MediaStream,
    {getAudioTracks: () => [{kind: 'audio'}]} as unknown as MediaStream);
  now = 2200;
  recording.pause();
  expect(recording.elapsed(1100)).toBe(1000);
  expect(recording.elapsed(2100)).toBe(2000);
  now = 7200;
  recording.resume();
  expect(recording.elapsed(1100)).toBe(1000);
  expect(recording.elapsed(2100)).toBe(2000);
  now = 8200;
  expect(recording.elapsed()).toBe(3100);
  await recording.stop();
  now += 1000;
  await recording.stop();
  expect(recording.elapsed()).toBe(3100);
});
