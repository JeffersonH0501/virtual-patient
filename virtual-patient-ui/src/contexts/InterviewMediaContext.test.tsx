import {act, cleanup, render, renderHook, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {PropsWithChildren, useEffect} from 'react';
import {InterviewMediaProvider} from './InterviewMediaContext';
import {useInterviewMedia} from './interviewMedia';

const stop = vi.fn();
const camera = {
  active: true,
  getTracks: () => [{stop}],
  getVideoTracks: () => [new EventTarget()],
} as unknown as MediaStream;
const microphone = {
  active: true,
  getTracks: () => [{stop}],
  getAudioTracks: () => [new EventTarget()],
} as unknown as MediaStream;
let interviewId: string | undefined;
let capturing = true;
beforeEach(() => {
  stop.mockReset();
  interviewId = undefined;
  capturing = true;
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: vi.fn(async (constraints) => (constraints.video ? camera : microphone)),
    },
  });
});
afterEach(cleanup);
const wrapper = ({children}: PropsWithChildren) => (
  <InterviewMediaProvider interviewId={interviewId} capturing={capturing}>{children}</InterviewMediaProvider>
);

it('keeps the exact calibrated streams when binding the newly created interview', async () => {
  const {result, rerender} = renderHook(useInterviewMedia, {wrapper});
  await act(async () => {
    await result.current.startCamera('external-camera');
    await result.current.startMicrophone('external-microphone');
  });
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith(expect.objectContaining({
    video: expect.objectContaining({deviceId: {exact: 'external-camera'}}),
  }));
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith(expect.objectContaining({
    audio: expect.objectContaining({deviceId: {exact: 'external-microphone'}}),
  }));
  act(() => result.current.bindInterview?.('7'));
  interviewId = '7';
  rerender();
  expect(result.current.cameraStream).toBe(camera);
  expect(result.current.microphoneStream).toBe(microphone);
  await act(async () => {
    await result.current.startCamera();
    await result.current.startMicrophone();
  });
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2);
  expect(stop).not.toHaveBeenCalled();
});

it('releases the old camera without stopping the microphone when selecting another camera', async () => {
  const {result} = renderHook(useInterviewMedia, {wrapper});
  await act(async () => {
    await result.current.startCamera();
    await result.current.startMicrophone();
  });
  await act(async () => result.current.startCamera('external-camera'));
  expect(stop).toHaveBeenCalledTimes(1);
  expect(result.current.cameraDeviceId).toBe('external-camera');
  expect(result.current.microphoneStream).toBe(microphone);
});

it('releases both devices when leaving for another interview without a calibrated handoff', async () => {
  const {result, rerender} = renderHook(useInterviewMedia, {wrapper});
  await act(async () => {
    await result.current.startCamera();
    await result.current.startMicrophone();
  });
  interviewId = '8';
  rerender();
  expect(stop).toHaveBeenCalledTimes(2);
  expect(result.current.cameraStream).toBeNull();
});

it('releases the camera and microphone when leaving calibration or the session', async () => {
  const {result, rerender} = renderHook(useInterviewMedia, {wrapper});
  await act(async () => {
    await result.current.startCamera();
    await result.current.startMicrophone();
  });
  capturing = false;
  rerender();
  expect(stop).toHaveBeenCalledTimes(2);
  expect(result.current.cameraStream).toBeNull();
  expect(result.current.microphoneStream).toBeNull();
  expect(result.current.cameraState).toBe('idle');
});
it('grants camera and microphone when resuming calibration from the session route of the same interview', async () => {
  // Resuming leaves /interviews/:id/session (interviewId set) for /calibration (no interviewId) and mounts the
  // calibration screen, which asks for both devices in its own effect during that same navigation.
  const Probe = () => {
    const media = useInterviewMedia();
    useEffect(() => {
      void Promise.all([media.startCamera(), media.startMicrophone()]);
    }, [media.startCamera, media.startMicrophone]);
    return <span data-testid="devices">{media.cameraState}/{media.microphoneState}</span>;
  };
  const view = render(<InterviewMediaProvider interviewId="6837" capturing>{null}</InterviewMediaProvider>);
  view.rerender(<InterviewMediaProvider interviewId={undefined} capturing><Probe /></InterviewMediaProvider>);
  await waitFor(() => expect(screen.getByTestId('devices').textContent).toBe('ready/ready'));
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2);
});
