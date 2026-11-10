import {act, cleanup, render, screen} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {GazeTest} from './GazeTest';

const geometry = vi.hoisted(() => ({viewportWidth: 1000, viewportHeight: 700, screenWidth: 1000,
  screenHeight: 700, devicePixelRatio: 1, orientation: 'landscape' as const, videoWidth: 640, videoHeight: 480}));
const processFrame = vi.hoisted(() => vi.fn());
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('../../hooks/useTechnicalCalibration', () => ({readGeometry: () => geometry}));
vi.mock('../../services/interviews/calibration', () => ({processGazeTestFrame: processFrame}));

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); processFrame.mockReset(); });

it('reports live estimates and becomes indeterminate when geometry changes', async () => {
  vi.useFakeTimers();
  Object.defineProperty(HTMLMediaElement.prototype, 'readyState', {configurable: true, get: () => 4});
  Object.defineProperties(HTMLVideoElement.prototype, {
    videoWidth: {configurable: true, get: () => 640},
    videoHeight: {configurable: true, get: () => 480},
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({drawImage: vi.fn()} as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((callback) => callback(new Blob(['frame'], {type: 'image/jpeg'})));
  processFrame.mockResolvedValue('inside');
  render(<GazeTest stream={{active: true, getVideoTracks: () => [{readyState: 'live', muted: false}]} as unknown as MediaStream} attemptId="attempt" gazeToken="gaze" cameraToken="camera"
    geometry={geometry} onRestart={vi.fn()} onExit={vi.fn()} />);
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(screen.getByRole('status').textContent).toBe('calibration.gazeTest.inside');
  expect(processFrame).toHaveBeenCalledOnce();
  act(() => window.dispatchEvent(new Event('resize')));
  expect(screen.getByRole('status').textContent).toBe('calibration.gazeTest.indeterminate');
  expect(screen.getByRole('alert').textContent).toBe('calibration.gazeTest.recalibrate');
});
