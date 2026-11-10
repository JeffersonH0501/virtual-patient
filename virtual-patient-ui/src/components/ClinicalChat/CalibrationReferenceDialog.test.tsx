import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {createInstance} from 'i18next';
import {I18nextProvider} from 'react-i18next';
import en from '../../i18n/locales/en.json';
import {CalibrationReferenceDialog} from './CalibrationReferenceDialog';

const api = vi.hoisted(() => ({load: vi.fn(), role: 'superuser'}));
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {role: api.role}})}));
vi.mock('../../services/interviews/calibrationReference', () => ({getCalibrationReference: api.load}));
vi.mock('../common/Dialog', () => ({Dialog: ({open, onClose, children}: {open: boolean; onClose: () => void; children: React.ReactNode}) => open ? <div role="dialog"><button onClick={onClose}>Close</button>{children}</div> : null}));
const i18n = createInstance();
await i18n.init({lng: 'en', resources: {en: {translation: en}}, interpolation: {escapeValue: false}});
const view = () => render(<I18nextProvider i18n={i18n}><CalibrationReferenceDialog interviewId={76} /></I18nextProvider>);
afterEach(() => {cleanup(); vi.clearAllMocks(); api.role = 'superuser';});

it('retains a not-passed checkpoint label when an experiment was allowed to continue', async () => {
  api.load.mockResolvedValue({calibration:null,captures:[{id:'experimental',stage:'gaze',durationMs:15000,
    mediaUrl:null,usedFor:[],metadata:{},result:{passed:false,experimentalQualityBypass:true,
      quality:{leaveOneTargetOut:{medianNormalizedError:.159,p90NormalizedError:.238}}}}]});
  view();
  fireEvent.click(screen.getByRole('button',{name:'Calibration'}));
  await screen.findByText('Gaze: Not passed');
  expect(screen.getByText(/quality limits were not passed/)).toBeDefined();
});

it('loads only when opened and shows retained video, checkpoint results and accepted references', async () => {
  api.load.mockResolvedValue({calibration: {status: 'passed'}, captures: [{id: 'capture', stage: 'unified', durationMs: 23000,
    mediaUrl: '/medical-interviews/76/calibration/captures/capture/video', usedFor: ['gaze'], metadata: {targets: []},
    result: {gaze: {passed: true, quality: {coveredTargets: 9}}, camera: {passed: false, quality: {cameraRadiusP90: .7}}}}]});
  const {container} = view();
  expect(api.load).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'Calibration'}));
  await screen.findByText('Gaze: Passed');
  expect(screen.getByText('Camera: Not passed')).toBeTruthy();
  expect(screen.getByText('Used for this interview: Gaze.')).toBeTruthy();
  expect(container.querySelector('video')?.getAttribute('src')).toContain('/76/calibration/captures/capture/video');
  expect(screen.getByText('Points with sufficient data (out of 9)')).toBeTruthy();
  expect(screen.getByText('View the accepted interview calibration')).toBeTruthy();
  fireEvent.error(container.querySelector('video')!);
  expect(screen.getByRole('alert').textContent).toBe(en.calibrationReference.videoUnavailable);
  fireEvent.click(screen.getByRole('button', {name: 'Close'}));
  expect(container.querySelector('video')).toBeNull();
});

it('shows legacy absence and retries failed loading', async () => {
  api.load.mockRejectedValueOnce(new Error('Synthetic network failure')).mockResolvedValueOnce({calibration: null, captures: []});
  view();
  fireEvent.click(screen.getByRole('button', {name: 'Calibration'}));
  await screen.findByRole('alert');
  fireEvent.click(screen.getByRole('button', {name: 'Try again'}));
  expect(await screen.findByText(en.calibrationReference.empty)).toBeTruthy();
});

it('keeps diagnostics available when video retention has expired', async () => {
  api.load.mockResolvedValue({calibration: null, captures: [{id: 'expired', stage: 'camera', durationMs: 5000, mediaUrl: null, usedFor: [], metadata: {}, result: {passed: false}}]});
  const {container} = view();
  fireEvent.click(screen.getByRole('button', {name: 'Calibration'}));
  expect(await screen.findByText(en.calibrationReference.videoUnavailable)).toBeTruthy();
  expect(screen.getByText('Camera: Not passed')).toBeTruthy();
  expect(container.querySelector('video')).toBeNull();
});

it.each(['student', 'teacher'])('does not expose inspection or fetch data for %s', (role) => {
  api.role = role;
  view();
  expect(screen.queryByRole('button')).toBeNull();
  expect(api.load).not.toHaveBeenCalled();
});

it('sums measured processing times across calibration and guided captures', async () => {
  api.load.mockResolvedValue({calibration: null, captures: [
    {id: 'one', stage: 'unified', durationMs: 23000, mediaUrl: null, usedFor: [], metadata: {},
      result: {passed: true, processingTimeSeconds: 2.25}},
    {id: 'two', stage: 'guided', durationMs: 76000, mediaUrl: null, usedFor: [], metadata: {},
      result: {passed: true, processingTimeSeconds: 3.5, guidedChecks: {
        version: 'guided_checks_v4_orientation', diagnosticOnly: true, promptLabelsVerified: false,
        processingTimeSeconds: 3.5, phases: [],
      }}},
  ]});
  view();
  fireEvent.click(screen.getByRole('button', {name: 'Calibration'}));
  expect(await screen.findByText('Total test processing time (all captures): 5.75 s')).toBeTruthy();
  expect(screen.getByText('Total processing time: 3.50 s')).toBeTruthy();
});

it('does not invent a complete total when a historical capture has no measurement', async () => {
  api.load.mockResolvedValue({calibration: null, captures: [
    {id: 'legacy', stage: 'camera', durationMs: 5000, mediaUrl: null, usedFor: [], metadata: {}, result: {passed: true}},
  ]});
  view();
  fireEvent.click(screen.getByRole('button', {name: 'Calibration'}));
  await screen.findByText('Camera: Passed');
  expect(screen.queryByText(/Total test processing time/)).toBeNull();
});
