import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {ComponentProps, StrictMode} from 'react';
import {createInstance} from 'i18next';
import {I18nextProvider} from 'react-i18next';
import en from '../../i18n/locales/en.json';
import es from '../../i18n/locales/es.json';
import {CalibrationActiveStep, CalibrationCheckpoint, CalibrationPreparation, GuidedCheckResults} from './CalibrationWizard';

const i18n = createInstance();
await i18n.init({
  lng: 'en',
  resources: {en: {translation: en}},
  interpolation: {escapeValue: false},
});

const defaults = () => ({
  cameraStream: {} as MediaStream,
  cameraState: 'ready' as const,
  microphoneState: 'ready' as const,
  audioLevel: 0,
  devicesReady: true,
  onStart: vi.fn(),
  onBack: vi.fn(),
  onRetryCamera: vi.fn(),
  onRetryMicrophone: vi.fn(),
  cameraDeviceId: '',
  microphoneDeviceId: '',
  onSelectCamera: vi.fn(),
  onSelectMicrophone: vi.fn(),
});
const preparation = (props: ComponentProps<typeof CalibrationPreparation>) => (
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <CalibrationPreparation {...props} />
    </I18nextProvider>
  </StrictMode>
);

afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('explains five-point validation error separately from valid sample coverage', () => {
  render(<I18nextProvider i18n={i18n}><CalibrationCheckpoint stage="gaze" passed={false} failureReason="p90_error"
    onStart={vi.fn()} titleRef={{current: null}} diagnostics={{version: 'mediapipe_five_point_quality_v1',
      targets: {BOTTOM_RIGHT: {eligible: true, validSamples: 12, validRatio: .7, validDurationMs: 1100}},
      leaveOneTargetOut: {medianNormalizedError: .1, p90NormalizedError: .31, perTarget: {BOTTOM_RIGHT: {p90NormalizedError: .51}}},
      qualityLimits: {medianNormalizedError: .15, p90NormalizedError: .3}}} /></I18nextProvider>);
  fireEvent.click(screen.getByText('Calibration quality by point'));
  expect(screen.getByText(/median 10.0%.*P90 31.0%/)).toBeDefined();
  expect(screen.getByText('51.0%')).toBeDefined();
  expect(screen.getByText('70.0%')).toBeDefined();
  expect(screen.getByText('1.10 s')).toBeDefined();
});

it('allows an experimental continuation while clearly retaining failed quality results', () => {
  const onContinue = vi.fn();
  render(<I18nextProvider i18n={i18n}><CalibrationCheckpoint stage="gaze" passed experimentalOverride
    failureReason="median_error" onStart={vi.fn()} onContinue={onContinue} titleRef={{current: null}}
    diagnostics={{version:'mediapipe_five_point_quality_v2',targets:{},
      leaveOneTargetOut:{medianNormalizedError:.259,p90NormalizedError:.338},
      qualityLimits:{medianNormalizedError:.25,p90NormalizedError:.35}}} /></I18nextProvider>);
  expect(screen.getByRole('heading',{name:'Continue with out-of-limit calibration'})).toBeDefined();
  expect(screen.getByText(/quality limits were not passed/)).toBeDefined();
  fireEvent.click(screen.getByText('Calibration quality by point'));
  expect(screen.getByText(/median 25.9%.*limit 25.0%.*P90 33.8%.*limit 35.0%/)).toBeDefined();
  fireEvent.click(screen.getByRole('button',{name:'Start interview'}));
  expect(onContinue).toHaveBeenCalledOnce();
});

it('offers an optional guided check without replacing ordinary calibration', () => {
  const onStartGuided = vi.fn();
  const props = defaults();
  render(preparation({...props, onStartGuided}));
  fireEvent.click(screen.getByRole('button', {name: 'Understood'}));
  fireEvent.click(screen.getByRole('button', {name: 'Start guided test'}));
  expect(onStartGuided).toHaveBeenCalledOnce();
  expect(onStartGuided).toHaveBeenCalledWith({deviceType: 'laptop', cameraPosition: 'top'});
  expect(props.onStart).not.toHaveBeenCalled();
});

it('paces three distinct nod cues without assuming the lens is above the screen', () => {
  const step = (remainingMs: number) => <I18nextProvider i18n={i18n}><CalibrationActiveStep phase="guided_check" activeCheck="nod_three" remainingMs={remainingMs} seconds={Math.ceil(remainingMs/1000)} titleRef={{current: null}} /></I18nextProvider>;
  const {rerender} = render(step(10000));
  expect(screen.getByText('Get ready to nod once with each number')).toBeDefined();
  rerender(step(9000));
  expect(screen.getByText('Nod once: 1 of 3')).toBeDefined();
  rerender(step(6000));
  expect(screen.getByText('Nod once: 2 of 3')).toBeDefined();
  rerender(step(3000));
  expect(screen.getByText('Nod once: 3 of 3')).toBeDefined();
});

it('shows unavailable diagnostic samples separately from observed zero activity', () => {
  render(<I18nextProvider i18n={i18n}><GuidedCheckResults diagnostics={{version: 'guided_checks_v1', diagnosticOnly: true, promptLabelsVerified: false,
    phases: [{kind: 'smile_speech', status: 'available', gazeValidRatio: null, gazeErrorMedian: null, smileActivityRatio: 0},
      {kind: 'gaze_turn', status: 'insufficient_signal', gazeValidRatio: null, gazeErrorMedian: null, smileActivityRatio: null},
      {kind: 'nod_three', status: 'insufficient_signal', gazeValidRatio: null, gazeErrorMedian: null, smileActivityRatio: null, nodCount: null, promptedNodCount: 3}]}} /></I18nextProvider>);
  expect(screen.getByText('Activity detected in 0% of samples')).toBeDefined();
  expect(screen.getByText(/Gaze available in/).textContent).not.toContain('0%');
  expect(screen.getByText(/prompt: 3 nods/).textContent).not.toContain('Detected: 0');
});

it('explains why a nod result is unavailable using signal coverage', () => {
  render(<I18nextProvider i18n={i18n}><GuidedCheckResults diagnostics={{version: 'guided_checks_v4_orientation', diagnosticOnly: true, promptLabelsVerified: false,
    phases: [{kind: 'nod_three', status: 'insufficient_signal', gazeValidRatio: null, gazeErrorMedian: null,
      smileActivityRatio: null, nodCount: null, promptedNodCount: 3, sampleCount: 40, faceValidRatio: .7,
      nodEvaluableWindows: 25, nodWindowCoverage: .4, nodUnavailableReason: 'insufficient_signal'}]}} /></I18nextProvider>);
  expect(screen.getByText('Samples: 40 · valid face: 70%')).toBeDefined();
  expect(screen.getByText('Evaluable windows: 25 · coverage: 40% (minimum 80%)')).toBeDefined();
  expect(screen.getByText('Insufficient signal to evaluate this phase.')).toBeDefined();
});

it('shows guided results and the video without opening a collapsed panel', () => {
  render(<I18nextProvider i18n={i18n}><CalibrationCheckpoint stage="gaze" passed onStart={vi.fn()}
    titleRef={{current: null}} guidedVideoUrl="blob:guided" guidedDiagnostics={{
      version: 'guided_checks_v4_orientation', diagnosticOnly: true, promptLabelsVerified: false,
      phases: [{kind: 'smile_speech', status: 'available', gazeValidRatio: null,
        gazeErrorMedian: null, smileActivityRatio: .5}],
    }} /></I18nextProvider>);
  expect(screen.getByText('Activity detected in 50% of samples').closest('details:not([open])')).toBeNull();
  expect(screen.getByLabelText('Temporary nonverbal test video').getAttribute('src')).toBe('blob:guided');
});

it('lists camera and microphone inputs separately and reports the selected devices', async () => {
  const mediaDevices = new EventTarget();
  Object.assign(mediaDevices, {enumerateDevices: async () => [
    {kind: 'videoinput', deviceId: 'camera-2', label: 'USB camera'},
    {kind: 'audioinput', deviceId: 'mic-2', label: 'USB microphone'},
    {kind: 'audiooutput', deviceId: 'speakers', label: 'Speakers'},
  ]});
  vi.stubGlobal('navigator', {mediaDevices});
  const props = defaults();
  render(preparation(props));
  fireEvent.click(screen.getByRole('button', {name: 'Understood'}));
  await screen.findByRole('option', {name: 'USB camera'});
  const camera = screen.getByRole('combobox', {name: 'Camera'});
  const microphone = screen.getByRole('combobox', {name: 'Microphone'});
  expect(within(camera).queryByRole('option', {name: 'USB microphone'})).toBeNull();
  expect(screen.queryByRole('option', {name: 'Speakers'})).toBeNull();
  fireEvent.change(camera, {target: {value: 'camera-2'}});
  fireEvent.change(microphone, {target: {value: 'mic-2'}});
  expect(props.onSelectCamera).toHaveBeenCalledWith('camera-2');
  expect(props.onSelectMicrophone).toHaveBeenCalledWith('mic-2');
});

it('requires an explicit acknowledgement before enabling preparation', () => {
  vi.useFakeTimers();
  const props = defaults();
  const view = render(preparation(props));
  const dialog = screen.getByRole('dialog', {name: 'Calibration'});
  expect(view.container.querySelector('.calibration-preparation-grid')).toBeNull();
  expect(view.container.querySelector('video')).toBeNull();
  expect(screen.queryByRole('combobox')).toBeNull();
  expect(screen.queryByRole('button', {name: en.calibration.startCalibration})).toBeNull();
  expect(within(dialog).queryByRole('button', {name: 'Close'})).toBeNull();
  expect(within(dialog).getByText(en.calibration.wizard.information.description)).toBeDefined();
  const acknowledge = within(dialog).getByRole('button', {name: 'Understood'});
  expect((acknowledge as HTMLButtonElement).disabled).toBe(false);
  expect(props.onStart).not.toHaveBeenCalled();
  fireEvent.click(acknowledge);
  expect(view.container.querySelector('video')).not.toBeNull();
  expect(screen.getAllByRole('combobox')).toHaveLength(2);
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(view.container.querySelector('.calibration-recommendations')).toBeNull();
  expect(screen.queryByRole('button', {name: en.common.back})).toBeNull();
  const start = screen.getByRole('button', {name: en.calibration.startCalibration});
  expect((start as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(start);
  expect(props.onStart).toHaveBeenCalledTimes(1);
});

it('allows returning immediately, maps Escape to returning', () => {
  vi.useFakeTimers();
  const props = defaults();
  const view = render(preparation(props));
  const dialog = screen.getByRole('dialog');
  fireEvent.click(document.body);
  expect(screen.getByRole('dialog')).toBe(dialog);
  fireEvent.keyDown(document, {key: 'Escape', keyCode: 27});
  expect(props.onBack).toHaveBeenCalledTimes(1);
  fireEvent.click(within(dialog).getByRole('button', {name: 'Back'}));
  expect(props.onBack).toHaveBeenCalledTimes(2);
  view.unmount();
  // Allow the shared portal's short removal timeout, while catching a leaked interval.
  act(() => vi.advanceTimersByTime(1000));
  expect(vi.getTimerCount()).toBe(0);
});

it('shows audio activity only on the camera outline without replacing its video or adding a preparation meter', () => {
  vi.useFakeTimers();
  const props = defaults();
  const view = render(preparation(props));
  fireEvent.click(screen.getByRole('button', {name: 'Understood'}));
  const camera = view.container.querySelector('.calibration-camera')!;
  const video = camera.querySelector('video')!;
  expect(camera.getAttribute('data-sound-active')).toBe('false');
  expect(screen.queryByRole('meter')).toBeNull();
  expect(video.srcObject).toBe(props.cameraStream);
  view.rerender(preparation({...props, audioLevel: 0.3}));
  expect(camera.getAttribute('data-sound-active')).toBe('true');
  expect(camera.querySelector('video')).toBe(video);
  view.rerender(preparation({...props, audioLevel: 0}));
  expect(camera.getAttribute('data-sound-active')).toBe('false');
  view.rerender(
    preparation({
      ...props,
      audioLevel: 0.4,
      microphoneState: 'permission-denied',
      devicesReady: false,
    }),
  );
  expect(camera.getAttribute('data-sound-active')).toBe('false');
  expect(screen.queryByRole('alert')).toBeNull();
  expect(view.container.querySelectorAll('[data-failed="true"]')).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', {name: /try again.*microphone/i}));
  expect(props.onRetryMicrophone).toHaveBeenCalledTimes(1);
  expect(props.onRetryCamera).not.toHaveBeenCalled();
});



it('places the camera preview before device selectors and the start action', () => {
  const view = render(preparation(defaults()));
  fireEvent.click(screen.getByRole('button', {name: 'Understood'}));
  const preview = view.container.querySelector('.calibration-preparation-media')!;
  const selectors = view.container.querySelector('.calibration-device-list')!;
  const start = screen.getByRole('button', {name: en.calibration.startCalibration});
  expect(preview.compareDocumentPosition(selectors) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(selectors.compareDocumentPosition(start) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it.each([['en', en], ['es', es]] as const)('shows translated completion text in %s', async (language, catalog) => {
  const instance = createInstance();
  await instance.init({lng: language, resources: {[language]: {translation: catalog}}, interpolation: {escapeValue: false}});
  const restart = vi.fn();
  render(<I18nextProvider i18n={instance}><CalibrationCheckpoint stage="camera" passed onStart={vi.fn()} onRestart={restart} onContinue={vi.fn()} titleRef={{current: null}} /></I18nextProvider>);
  expect(screen.getByRole('heading', {name: catalog.calibration.wizard.success.title})).toBeTruthy();
  expect(screen.getByRole('button', {name: catalog.calibration.startInterview})).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: catalog.calibration.restartCalibration}));
  expect(restart).toHaveBeenCalledOnce();
});


it('distinguishes precision failures from missing gaze samples', () => {
  render(<I18nextProvider i18n={i18n}><CalibrationCheckpoint stage="gaze" passed={false} failureReason="median_error" onStart={vi.fn()} titleRef={{current: null}} /></I18nextProvider>);
  expect(screen.getByRole('heading', {name: en.calibration.wizard.failures.precision.title})).toBeTruthy();
});

it('shows affected targets without technical extraction counts', () => {
  render(<I18nextProvider i18n={i18n}><CalibrationCheckpoint stage="gaze" passed={false} failureReason="targets" diagnostics={{targets: {BOTTOM_LEFT: {eligible: false, invalidReasons: {eyesClosed: 4}}}}} onStart={vi.fn()} titleRef={{current: null}} /></I18nextProvider>);
  expect(screen.getByRole('heading', {name: en.calibration.wizard.failures.coverage.title})).toBeTruthy();
  expect(screen.getByText(/Bottom left/)).toBeTruthy();
  expect(screen.queryByRole('list')).toBeNull();
  expect(screen.queryByText(/Eye opening|detector|: 4/i)).toBeNull();
});


it.each([['en', en], ['es', es]] as const)('shows a simple camera retry message without detector counts in %s', async (language, catalog) => {
  const instance = createInstance();
  await instance.init({lng: language, resources: {[language]: {translation: catalog}}, interpolation: {escapeValue: false}});
  render(<I18nextProvider i18n={instance}><CalibrationCheckpoint stage="camera" passed={false} failureReason="camera_unstable" diagnostics={{invalidReasons: {eyesClosed: 1, inferenceFailed: 2}}} onStart={vi.fn()} titleRef={{current: null}} /></I18nextProvider>);
  expect(screen.getByRole('heading', {name: catalog.calibration.wizard.failures.cameraStability.title})).toBeTruthy();
  expect(screen.getByText(catalog.calibration.wizard.failures.cameraStability.advice)).toBeTruthy();
  expect(screen.getByRole('button', {name: catalog.calibration.retryCamera})).toBeTruthy();
  expect(screen.queryByRole('list')).toBeNull();
  expect(screen.queryByText(/detector|: 1|: 2/i)).toBeNull();
});
