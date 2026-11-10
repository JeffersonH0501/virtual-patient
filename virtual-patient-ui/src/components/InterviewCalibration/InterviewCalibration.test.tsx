import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {StrictMode, useState} from 'react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, expect, it, vi} from 'vitest';
import {InterviewCalibration} from '.';

const api = vi.hoisted(() => ({
  createInterview: vi.fn(),
  processCalibrationStage: vi.fn(),
  processNonverbalTest: vi.fn(),
  saveCalibrationResult: vi.fn(),
  startInterview: vi.fn(),
  warmUpCalibration: vi.fn().mockResolvedValue(undefined),
  discardCalibrationDraft: vi.fn().mockResolvedValue(undefined),
  discardResumeCalibration: vi.fn().mockResolvedValue(undefined),
  getInterview: vi.fn(),
}));
const media = vi.hoisted(() => ({
  cameraState: 'ready', microphoneState: 'ready',
  cameraStream: null as MediaStream | null,
  startCamera: vi.fn(), startMicrophone: vi.fn(), bindInterview: vi.fn(),
}));
const captureControl = vi.hoisted(() => ({hold: false, cancel: vi.fn(), start: vi.fn()}));
const activeCapture = vi.hoisted(() => vi.fn(() => null));

vi.mock('react-i18next', () => ({useTranslation: () => ({i18n: {}, t: (key: string) => key})}));
vi.mock('../../contexts/interviewMedia', () => ({useInterviewMedia: () => media}));
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {role: 'superuser'}})}));
vi.mock('../../services/interviews', () => api);
vi.mock('../../services/interviews/calibration', () => ({processNonverbalTest: api.processNonverbalTest}));
vi.mock('../../services/interviews/createInterview', () => ({createInterview: api.createInterview}));
vi.mock('./GazeTest', () => ({GazeTest: () => <p>Live gaze test</p>}));
vi.mock('../common/Dialog', () => ({Dialog: ({open, children, actions}: {open: boolean; children: React.ReactNode; actions: React.ReactNode}) => open ? <div role="dialog">{children}{actions}</div> : null}));
vi.mock('../../hooks/useTechnicalCalibration', () => ({
  useTechnicalCalibration: () => {
    const [phase, setPhase] = useState('idle');
    const [capture, setCapture] = useState<{stage: string; blob: Blob} | null>(null);
    return {
      media: capture, phase, reset: () => {
 setCapture(null); setPhase('idle');
},
      cancel: () => {
 captureControl.cancel(); setPhase('error');
},
      failureReason: 'capture_interrupted',
      start: (stage: string, metadata: Record<string, unknown>) => {
 captureControl.start(stage, metadata);
 setPhase(captureControl.hold ? 'gaze_targets' : 'complete'); if (!captureControl.hold) setCapture({stage, blob: new Blob([stage])});
},
    };
  },
}));
vi.mock('./CalibrationWizard', () => ({
  CalibrationPreparation: ({onStart, onStartGuided, devicesReady}: {onStart: () => void; onStartGuided: (environment: {deviceType: string; cameraPosition: string}) => void; devicesReady: boolean}) => <>
    <button disabled={!devicesReady} onClick={onStart}>Prepare</button>
    <button disabled={!devicesReady} onClick={() => onStartGuided({deviceType: 'tablet', cameraPosition: 'left'})}>Guided check</button>
  </>,
  CalibrationActiveStep: activeCapture,
  CalibrationProcessing: () => <p>Checking calibration</p>,
  CalibrationCheckpoint: ({onStart, onContinue, passed, failureReason, error, busy, guidedVideoUrl}: {
    onStart: () => void; onContinue?: () => void; passed?: boolean;
    failureReason?: string; error?: boolean; busy?: boolean; guidedVideoUrl?: string | null;
  }) => <>
    {guidedVideoUrl && <video src={guidedVideoUrl} aria-label="calibration.guided.testVideo" />}
    {failureReason && <p>{failureReason}</p>}
    {error && <p>Start failed</p>}
    {passed ? <button disabled={busy} onClick={onContinue}>Continue</button> : <button disabled={busy} onClick={onStart}>Capture or retry</button>}
  </>,
}));

afterEach(async () => {
 cleanup(); await Promise.resolve(); captureControl.hold = false; vi.clearAllMocks(); api.discardCalibrationDraft.mockReset().mockResolvedValue(undefined);
 media.cameraStream = null;
});

it('opens the live gaze view only after successful test calibration', async () => {
  media.cameraStream = {} as MediaStream;
  api.processNonverbalTest.mockResolvedValueOnce({stage: 'unified', status: 'passed', result: {checkpoints: {
    gaze: {stage: 'gaze', status: 'passed', attestation: 'gaze', result: {profile: {captureGeometry: {}}}},
    camera: {stage: 'camera', status: 'passed', attestation: 'camera', result: {}},
  }}});
  render(<MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {clinicalCaseId: 1, patientResponseLanguage: 'en', gazeTest: true}}]}>
    <InterviewCalibration />
  </MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', {name: 'Prepare'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Continue'}));
  expect(await screen.findByText('Live gaze test')).toBeDefined();
  expect(api.createInterview).not.toHaveBeenCalled();
  expect(api.saveCalibrationResult).not.toHaveBeenCalled();
});

it('starts optional guided capture without changing the ordinary start option', async () => {
  api.createInterview.mockResolvedValue({id: 42});
  captureControl.hold = true;
  render(<MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {clinicalCaseId: 1, patientResponseLanguage: 'en', calibrationTest: true}}]}>
    <InterviewCalibration />
  </MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', {name: 'Guided check'}));
  await screen.findByRole('button', {name: 'calibration.exitTitle'});
  expect(captureControl.start).toHaveBeenCalledWith('guided', {
    guidedEnvironment: {deviceType: 'tablet', cameraPosition: 'left'}, nonverbalOnly: true, attestations: {},
  });
});

it('runs the temporary guided test without creating an interview', async () => {
  Object.assign(URL, {createObjectURL: vi.fn(() => 'blob:temporary'), revokeObjectURL: vi.fn()});
  api.createInterview.mockResolvedValue({id:42});
  api.processNonverbalTest.mockResolvedValueOnce({stage:'guided',status:'passed',result:{guidedChecks:{phases:[]}}});
  render(<MemoryRouter initialEntries={[{pathname:'/interviews/calibration',state:{clinicalCaseId:1,patientResponseLanguage:'en',calibrationTest:true}}]}>
    <InterviewCalibration />
  </MemoryRouter>);
  fireEvent.click(await screen.findByRole('button',{name:'Guided check'}));
  await screen.findByRole('button',{name:'Continue'});
  expect(captureControl.start).toHaveBeenLastCalledWith('guided',{
    guidedEnvironment:{deviceType:'tablet',cameraPosition:'left'},
    nonverbalOnly:true, attestations:{},
  });
  expect(api.saveCalibrationResult).not.toHaveBeenCalled();
  expect(api.createInterview).not.toHaveBeenCalled();
});

it('waits for guided processing before showing the results', async () => {
  Object.assign(URL, {createObjectURL: vi.fn(() => 'blob:temporary'), revokeObjectURL: vi.fn()});
  api.createInterview.mockResolvedValue({id: 42});
  let finish!: (result: unknown) => void;
  api.processNonverbalTest.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  render(<MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {clinicalCaseId: 1, patientResponseLanguage: 'en', calibrationTest: true}}]}>
    <InterviewCalibration />
  </MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', {name: 'Guided check'}));
  await screen.findByText('Checking calibration');
  expect(captureControl.start).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('button', {name: 'Continue'})).toBeNull();
  finish({stage: 'guided', status: 'passed', result: {guidedChecks: {phases: []}}});
  await screen.findByRole('button', {name: 'Continue'});
  expect(captureControl.start).toHaveBeenCalledTimes(1);
});

it('shows the temporary video and never creates or saves an interview', async () => {
  const revokeUrl = vi.fn();
  Object.assign(URL, {createObjectURL: vi.fn(() => 'blob:temporary'), revokeObjectURL: revokeUrl});
  api.processNonverbalTest.mockResolvedValueOnce({stage: 'guided', status: 'passed', result: {guidedChecks: {phases: []}}});
  const rendered = render(<MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {
    clinicalCaseId: 1, patientResponseLanguage: 'en', calibrationTest: true,
  }}]}><InterviewCalibration /></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', {name: 'Guided check'}));
  expect((await screen.findByLabelText('calibration.guided.testVideo')).getAttribute('src')).toBe('blob:temporary');
  expect(api.createInterview).not.toHaveBeenCalled();
  expect(api.saveCalibrationResult).not.toHaveBeenCalled();
  rendered.unmount();
  expect(revokeUrl).toHaveBeenCalledWith('blob:temporary');
});

it('reuses the draft request, the recorded clip, and the saved calibration after lost responses', async () => {
  api.createInterview.mockRejectedValueOnce(new TypeError('Offline')).mockResolvedValue({id: 42});
  api.processCalibrationStage.mockRejectedValueOnce(new TypeError('Offline')).mockImplementation(async (stage) => ({
    stage, status: 'passed', result: {checkpoints: {
      gaze: {stage: 'gaze', status: 'passed', attestation: 'gaze', result: {profile: {captureGeometry: {}, affineMatrix: []}}},
      camera: {stage: 'camera', status: 'passed', attestation: 'camera', result: {cameraReferenceCenter: [0, 0], neutralHead: {}}},
    }},
  }));
  api.saveCalibrationResult.mockRejectedValueOnce(new TypeError('Offline')).mockResolvedValue(undefined);

  render(<MemoryRouter initialEntries={[{
    pathname: '/interviews/calibration', state: {clinicalCaseId: 1, patientResponseLanguage: 'en'},
  }]}>
    <Routes>
      <Route path="/interviews/calibration" element={<InterviewCalibration />} />
      <Route path="/interviews/:interviewId/session" element={<h1>Session</h1>} />
    </Routes>
  </MemoryRouter>);

  const click = async (name: string) => fireEvent.click(await screen.findByRole('button', {name}));
  await click('Prepare');
  await screen.findByText('draft_create_failed');
  await click('Capture or retry');
  await screen.findByText('upload_failed');
  await click('Capture or retry');
  await click('Continue');
  await screen.findByText('Start failed');
  await click('Continue');
  await screen.findByRole('heading', {name: 'Session'});

  expect(api.createInterview).toHaveBeenCalledTimes(2);
  expect(api.createInterview.mock.calls[0][0]).toEqual(api.createInterview.mock.calls[1][0]);
  expect(api.processCalibrationStage.mock.calls[0][2]).toBe(api.processCalibrationStage.mock.calls[1][2]);
  expect(api.processCalibrationStage.mock.calls.map(([stage]) => stage)).toEqual(['unified', 'unified']);
  expect(api.saveCalibrationResult).toHaveBeenCalledTimes(2);
  expect(api.startInterview).not.toHaveBeenCalled();
  expect(api.discardCalibrationDraft).not.toHaveBeenCalled();
  expect(activeCapture).not.toHaveBeenCalled();
});


it('repeats only camera after a unified capture passes gaze', async () => {
  api.createInterview.mockResolvedValue({id: 42});
  api.startInterview.mockResolvedValue(undefined);
  const gaze = {stage: 'gaze', status: 'passed', attestation: 'gaze-token', result: {profile: {affineMatrix: [], captureGeometry: {}}}};
  const camera = {stage: 'camera', status: 'passed', attestation: 'camera-token', result: {cameraReferenceCenter: [0, 0], neutralHead: {}}};
  api.processCalibrationStage.mockImplementation(async (stage) => stage === 'unified'
    ? {stage, status: 'failed', failureReason: 'camera', result: {failedStage: 'camera', checkpoints: {gaze, camera: {stage: 'camera', status: 'failed', failureReason: 'camera'}}}}
    : camera);
  render(<MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {clinicalCaseId: 1, patientResponseLanguage: 'en'}}]}>
    <Routes><Route path="/interviews/calibration" element={<InterviewCalibration />} /><Route path="/interviews/:interviewId/session" element={<h1>Session</h1>} /></Routes>
  </MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', {name: 'Prepare'}));
  await screen.findByText('camera');
  fireEvent.click(await screen.findByRole('button', {name: 'Capture or retry'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Continue'}));
  await screen.findByRole('heading', {name: 'Session'});
  expect(api.processCalibrationStage.mock.calls.map(([stage]) => stage)).toEqual(['unified', 'camera']);
  expect(api.saveCalibrationResult.mock.calls[0][1].attestations).toEqual({gaze: 'gaze-token', camera: 'camera-token'});
});


it('keeps device preparation visible until capture starts without an intermediate screen', async () => {
  let created!: (value: {id: number}) => void;
  api.createInterview.mockReturnValueOnce(new Promise((resolve) => {
 created = resolve;
}));
  api.processCalibrationStage.mockReturnValue(new Promise(() => undefined));
  render(<MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {clinicalCaseId: 1, patientResponseLanguage: 'en'}}]}>
    <Routes><Route path="/interviews/calibration" element={<InterviewCalibration />} /></Routes>
  </MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', {name: 'Prepare'}));
  expect((screen.getByRole('button', {name: 'Prepare'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByText('Checking calibration')).toBeNull();
  created({id: 42});
  expect(await screen.findByText('Checking calibration')).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Prepare'})).toBeNull();
});


it('cancels capture before opening the exit dialog', async () => {
  captureControl.hold = true;
  api.createInterview.mockResolvedValue({id: 42});
  render(<MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {clinicalCaseId: 1, patientResponseLanguage: 'en'}}]}>
    <Routes><Route path="/interviews/calibration" element={<InterviewCalibration />} /></Routes>
  </MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', {name: 'Prepare'}));
  await screen.findByRole('button', {name: 'calibration.exitTitle'});
  fireEvent.click(screen.getByRole('button', {name: 'calibration.exitTitle'}));
  expect(captureControl.cancel).toHaveBeenCalledOnce();
  expect(await screen.findByRole('dialog')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'common.cancel'}));
  expect(await screen.findByText('capture_interrupted')).toBeTruthy();
  expect(api.processCalibrationStage).not.toHaveBeenCalled();
  expect(api.discardCalibrationDraft).not.toHaveBeenCalled();
});


const renderCalibrationWithExit = (strict = false) => {
  const route = <MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {clinicalCaseId: 1, patientResponseLanguage: 'en'}}]}>
    <Routes><Route path="/interviews/calibration" element={<InterviewCalibration />} /><Route path="/cases" element={<h1>Cases</h1>} /></Routes>
  </MemoryRouter>;
  return render(strict ? <StrictMode>{route}</StrictMode> : route);
};

const confirmCalibrationExit = async () => {
  fireEvent.click(screen.getByRole('button', {name: 'calibration.exitTitle'}));
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', {name: 'calibration.exitTitle'}));
};

it('waits for server deletion before leaving and allows retry when deletion fails', async () => {
  api.createInterview.mockResolvedValue({id: 42});
  api.processCalibrationStage.mockReturnValue(new Promise(() => undefined));
  api.discardCalibrationDraft.mockRejectedValueOnce(new TypeError('Offline')).mockResolvedValueOnce(undefined);
  renderCalibrationWithExit();
  fireEvent.click(screen.getByRole('button', {name: 'Prepare'}));
  await screen.findByText('Checking calibration');
  await confirmCalibrationExit();
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'calibration.discardError');
  expect(screen.queryByRole('heading', {name: 'Cases'})).toBeNull();
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'calibration.exitTitle'}));
  await screen.findByRole('heading', {name: 'Cases'});
  expect(api.discardCalibrationDraft.mock.calls).toEqual([[42], [42]]);
});

it('discards an unstarted draft on navigation without deleting during Strict Mode replay', async () => {
  api.createInterview.mockResolvedValue({id: 42});
  api.processCalibrationStage.mockReturnValue(new Promise(() => undefined));
  const view = renderCalibrationWithExit(true);
  expect(api.discardCalibrationDraft).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'Prepare'}));
  await screen.findByText('Checking calibration');
  view.unmount();
  await Promise.resolve();
  expect(api.discardCalibrationDraft).toHaveBeenCalledWith(42);
});

it('discards late draft creation after exit without starting capture', async () => {
  let created!: (value: {id: number}) => void;
  api.createInterview.mockReturnValueOnce(new Promise((resolve) => {
 created = resolve;
}));
  renderCalibrationWithExit();
  fireEvent.click(screen.getByRole('button', {name: 'Prepare'}));
  await confirmCalibrationExit();
  await screen.findByRole('heading', {name: 'Cases'});
  created({id: 42});
  await Promise.resolve();
  expect(api.discardCalibrationDraft).toHaveBeenCalledWith(42);
  expect(api.processCalibrationStage).not.toHaveBeenCalled();
});

it('sends best-effort discard on page hide', async () => {
  api.createInterview.mockResolvedValue({id: 42});
  api.processCalibrationStage.mockReturnValue(new Promise(() => undefined));
  renderCalibrationWithExit();
  fireEvent.click(screen.getByRole('button', {name: 'Prepare'}));
  await screen.findByText('Checking calibration');
  fireEvent(window, new Event('pagehide'));
  expect(api.discardCalibrationDraft).toHaveBeenCalledWith(42);
});

it('creates a fresh preparation after the server has discarded the old calibration', async () => {
  api.createInterview.mockResolvedValueOnce({id: 42}).mockResolvedValueOnce({id: 43});
  api.processCalibrationStage.mockRejectedValueOnce(Object.assign(new Error('Expired'), {status: 410})).mockReturnValueOnce(new Promise(() => undefined));
  renderCalibrationWithExit();
  fireEvent.click(screen.getByRole('button', {name: 'Prepare'}));
  await screen.findByText('draft_expired');
  fireEvent.click(screen.getByRole('button', {name: 'Capture or retry'}));
  await screen.findByText('Checking calibration');
  expect(api.createInterview).toHaveBeenCalledTimes(2);
  expect(api.createInterview.mock.calls[0][0].draft_request_id).not.toBe(api.createInterview.mock.calls[1][0].draft_request_id);
  expect(api.processCalibrationStage.mock.calls.map(([, id]) => id)).toEqual([42, 43]);
});

it('keeps the failure panel while retrying draft creation', async () => {
  api.createInterview.mockRejectedValueOnce(new TypeError('Offline')).mockReturnValueOnce(new Promise(() => undefined));
  render(<MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {clinicalCaseId: 1, patientResponseLanguage: 'en'}}]}>
    <Routes><Route path="/interviews/calibration" element={<InterviewCalibration />} /></Routes>
  </MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', {name: 'Prepare'}));
  await screen.findByText('draft_create_failed');
  fireEvent.click(screen.getByRole('button', {name: 'Capture or retry'}));
  expect(screen.getByText('draft_create_failed')).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Prepare'})).toBeNull();
  expect((screen.getByRole('button', {name: 'Capture or retry'}) as HTMLButtonElement).disabled).toBe(true);
});


it('does not start capture when draft creation completes after opening exit', async () => {
  let created!: (value: {id: number}) => void;
  api.createInterview.mockReturnValueOnce(new Promise((resolve) => {
 created = resolve;
}));
  render(<MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {clinicalCaseId: 1, patientResponseLanguage: 'en'}}]}>
    <Routes><Route path="/interviews/calibration" element={<InterviewCalibration />} /></Routes>
  </MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', {name: 'Prepare'}));
  fireEvent.click(screen.getByRole('button', {name: 'calibration.exitTitle'}));
  await screen.findByRole('dialog');
  created({id: 42});
  await screen.findByText('capture_interrupted');
  expect(api.processCalibrationStage).not.toHaveBeenCalled();
  expect(screen.queryByText('Checking calibration')).toBeNull();
  fireEvent.click(screen.getByRole('button', {name: 'common.cancel'}));
  expect((screen.getByRole('button', {name: 'Capture or retry'}) as HTMLButtonElement).disabled).toBe(false);
});

it('recalibrates the same started interview using only its authorized resume attempt', async () => {
  api.getInterview.mockResolvedValue({id: 7, status: 'in_progress', startTime: '2026-11-08T12:00:00Z'});
  api.processCalibrationStage.mockResolvedValue({stage: 'unified', status: 'passed', result: {checkpoints: {
    gaze: {stage: 'gaze', status: 'passed', attestation: 'gaze', result: {profile: {affineMatrix: [], captureGeometry: {}}}},
    camera: {stage: 'camera', status: 'passed', attestation: 'camera', result: {cameraReferenceCenter: [0, 0], neutralHead: {}}},
  }}});
  api.saveCalibrationResult.mockResolvedValue(undefined);
  render(<MemoryRouter initialEntries={[{pathname: '/interviews/calibration', state: {
    draftInterviewId: 7, resume: {resumeAttemptId: 'attempt', offsetMs: 60_000, pendingPatientMessageId: 12},
  }}]}><Routes>
    <Route path="/interviews/calibration" element={<InterviewCalibration />} />
    <Route path="/interviews/7/session" element={<h1>Resumed session</h1>} />
  </Routes></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', {name: 'Prepare'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Continue'}));
  await screen.findByRole('heading', {name: 'Resumed session'});
  expect(api.processCalibrationStage.mock.calls[0][1]).toBe(7);
  expect(api.processCalibrationStage.mock.calls[0][5]).toBe('attempt');
  expect(api.saveCalibrationResult).toHaveBeenCalledWith(7, expect.any(Object), 'attempt');
  expect(media.bindInterview).toHaveBeenCalledWith('7');
  expect(api.createInterview).not.toHaveBeenCalled();
  expect(api.startInterview).not.toHaveBeenCalled();
  expect(api.discardCalibrationDraft).not.toHaveBeenCalled();
});
