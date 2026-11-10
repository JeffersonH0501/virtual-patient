import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {ClinicalChat} from './index';
import type {ComponentProps, PropsWithChildren} from 'react';
import type {CallToolbar} from './CallToolbar';
import type {ConversationTranscript} from './ConversationTranscript';
import type {ClinicalHypotheses} from './ClinicalHypotheses';
import type {Dialog} from '../common/Dialog';
import type {Modal} from '../common/Modal';
import type {useHandsFreeSpeech} from '../../hooks/useHandsFreeSpeech';
import type {useInterviewRecording} from '../../hooks/useInterviewRecording';
import type {AssessmentSelector} from '../Evaluation/AssessmentSelector';
import type {User} from '../../types/user';
import type {Message} from '../../types';

const flow = vi.hoisted(() => ({
  interrupt: vi.fn(),
  role: 'student' as User['role'],
  userId: 1,
  routeId: '7',
  load: vi.fn(),
  profiles: [] as {route: string; account: number; summary: string}[],
  review: {} as ComponentProps<typeof AssessmentSelector>,
  recap: vi.fn(),
  regenerate: vi.fn(),
  reprocess: vi.fn(),
  resumeRecording: vi.fn(),
  resumeBlock: vi.fn(),
  recoverSegment: vi.fn(),
  toolbar: {} as ComponentProps<typeof CallToolbar>,
  transcript: {} as ComponentProps<typeof ConversationTranscript>,
  speechOptions: {} as Parameters<typeof useHandsFreeSpeech>[0],
  speechFrames: [] as {pending: boolean; paused: boolean}[],
  hypotheses: {} as ComponentProps<typeof ClinicalHypotheses>,
  humanRating: {} as ComponentProps<typeof import('../Evaluation/HumanRatingPanel').HumanRatingPanel>,
  speech: {
    isEnabled: true,
    isSubmittingUtterance: false,
    hasPendingUtterance: false,
    stop: vi.fn(),
  },
  recording: {
    syncPending: false,
    stopForRecovery: vi.fn(),
    status: 'recording',
    segmentId: 'synthetic-segment',
    captureSegmentId: 'synthetic-segment',
    isCapturing: true,
    sealForEnding: vi.fn(),
    canRestartWithCurrentGeometry: vi.fn(),
    restartAfterCancel: vi.fn(),
    recordWrittenPatientTurn: vi.fn(),
    endPatientTurn: vi.fn(),
    get canResume() {
      return this.status === 'paused';
    },
    pause: vi.fn(),
    resume: vi.fn(),
    finalize: vi.fn(),
    resumeAudioGraph: vi.fn(),
    recordStudentTurn: vi.fn(),
    endStudentTurn: vi.fn(),
    discardStudentTurn: vi.fn(),
    beginStudentTurn: vi.fn(),
    beginPatientTurn: vi.fn(),
    elapsedAt: () => 0,
  },
  media: {
    cameraState: 'ready',
    microphoneState: 'ready',
    startCamera: vi.fn(),
    startMicrophone: vi.fn(),
  },
  interview: {
    lifecycle: undefined as import('../../types/interview').CompleteInterviewResponse['lifecycle'],
    id: 7,
    isOwner: true,
    status: 'in_progress',
    startTime: '2026-11-02T12:00:00Z' as string | undefined,
    messages: [] as Message[],
    clinicalCase: {id: 1},
    progressSummary: undefined as {summaryText: string} | undefined,
    interviewMetadata: {} as {completionProcessing?: {status: 'failed'}},
    reviewAccess: undefined as {canViewAssessments: boolean; assignmentId: number | null; selfAssessmentRequired?: boolean} | undefined,
  },
  route: {pathname: '/interviews/7/session', state: {justStarted: true} as {justStarted: boolean; resume?: import('../../utils/routes').InterviewResumeState}},
  navigate: vi.fn(),
  redirects: [] as string[],
  send: vi.fn(),
  start: vi.fn(),
  summary: vi.fn(),
  fetchCount: 0,
  loadError: false,
  complete: vi.fn(),
  captureOptions: {} as Parameters<typeof useInterviewRecording>[0],
  t: (key: string) => key,
  motion: {enabled: false, reduced: true},
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({t: flow.t, i18n: {resolvedLanguage: 'en'}}),
}));
vi.mock('react-router-dom', () => ({
  useParams: () => ({interviewId: flow.routeId}),
  useNavigate: () => flow.navigate,
  useLocation: () => flow.route,
  Navigate: ({to}: {to: string}) => {
    flow.redirects.push(to);
    return null;
  },
}));
vi.mock('../../hooks/useUser', () => ({
  useUser: () => ({user: {id: flow.userId, role: flow.role, name: 'Synthetic student'}}),
}));
vi.mock('../../contexts/interviewMedia', () => ({useInterviewMedia: () => flow.media}));
vi.mock('../../hooks/useHandsFreeSpeech', () => ({
  useHandsFreeSpeech: (options: Parameters<typeof useHandsFreeSpeech>[0]) => {
    flow.speechOptions = options;
    flow.speechFrames.push({pending: flow.recording.syncPending, paused: options.paused});
    return flow.speech;
  },
}));
vi.mock('../../hooks/useInterviewRecording', () => ({
  useInterviewRecording: (options: Parameters<typeof useInterviewRecording>[0]) => {
    flow.captureOptions = options;
    return flow.recording;
  },
}));
vi.mock('../../services/interviews/getInterview', () => ({
  getInterview: async (id: string) => {
    flow.fetchCount += 1;
    if (flow.loadError) throw new Error('Synthetic load failure');
    return flow.load(id);
  },
}));
vi.mock('../../services/interviews', () => ({
  sendMessage: (...args: unknown[]) => flow.send(...args),
  createSummary: (...args: unknown[]) => flow.summary(...args),
  completeInterview: (...args: unknown[]) => flow.complete(...args),
  interruptInterview: flow.interrupt,
  startInterview: (...args: unknown[]) => flow.start(...args),
}));
vi.mock('../common/Motion/hooks', () => ({useAppMotion: () => flow.motion}));
vi.mock('../common', () => ({
  Modal: ({open, children}: ComponentProps<typeof Modal>) => (open ? children : null),
}));
vi.mock('../common/Dialog', () => ({
  Dialog: ({open, children, actions}: ComponentProps<typeof Dialog>) =>
    open ? (
      <section>
        {children}
        {actions}
      </section>
    ) : null,
}));
vi.mock('./InterviewLayouts', () => ({
  ActiveSimulationLayout: ({children}: PropsWithChildren) => <>{children}</>,
  SimulationResultsLayout: ({children}: PropsWithChildren) => <>{children}</>,
}));
vi.mock('./CallToolbar', () => ({
  CallTimer: ({elapsedSeconds}: {elapsedSeconds: number}) => <output aria-label="Elapsed time">{elapsedSeconds}</output>,
  CallToolbar: (props: ComponentProps<typeof CallToolbar>) => {
    flow.toolbar = props;
    return (
      <footer><button disabled={props.endDisabled} onClick={props.onEndInterview}>
        End
      </button></footer>
    );
  },
}));
vi.mock('./ConversationTranscript', () => ({
  ConversationTranscript: (props: ComponentProps<typeof ConversationTranscript>) => {
    flow.transcript = props;
    return <section aria-label="Interview conversation"><header>{props.headerAction}</header></section>;
  },
}));
vi.mock('./ClinicalHypotheses', () => ({
  ClinicalHypotheses: (props: ComponentProps<typeof ClinicalHypotheses>) => {
    flow.hypotheses = props;
    return <div data-testid="hypotheses" />;
  },
}));
vi.mock('./PatientProfile', () => ({
  PatientProfile: ({patient, children}: ComponentProps<typeof import('./PatientProfile').PatientProfile>) => {
    flow.profiles.push({route: flow.routeId, account: flow.userId, summary: patient.summary});
    return <section aria-label="Interview information">{patient.summary}{children}</section>;
  },
}));
vi.mock('./CallStage', () => ({CallStage: () => null}));
vi.mock('./WelcomeModal', () => ({WelcomeModal: ({isOpen, onAccept, busy, error}: ComponentProps<typeof import('./WelcomeModal').WelcomeModal>) =>
  isOpen ? <section role="dialog" aria-label="Instructions">
    <button disabled={busy} onClick={onAccept}>Accept instructions</button>
    {error && <p role="alert">Start failed</p>}
  </section> : null}));
vi.mock('../Evaluation/HumanRatingPanel', () => ({HumanRatingPanel: (props: ComponentProps<typeof import('../Evaluation/HumanRatingPanel').HumanRatingPanel>) => {
  flow.humanRating = props;
  return <section aria-label="Private rating form" />;
}}));
vi.mock('../Evaluation/AssessmentSelector', () => ({AssessmentSelector: (props: ComponentProps<typeof AssessmentSelector>) => {
  flow.review = props;
  return <button onClick={props.onRegenerate} disabled={props.refreshDisabled}>Regenerate</button>;
}}));
vi.mock('./InterviewRecap', () => ({InterviewRecap: () => <section aria-label="Interview recap" />}));
vi.mock('../../services/recordings', () => ({
  getInterviewRecap: (...args: unknown[]) => flow.recap(...args),
  regenerateInterviewEvaluation: (...args: unknown[]) => flow.regenerate(...args),
  reprocessInterviewRecording: (...args: unknown[]) => flow.reprocess(...args),
  resumeInterviewRecording: (...args: unknown[]) => flow.resumeRecording(...args),
  recoverInterviewSegment: (...args: unknown[]) => flow.recoverSegment(...args),
}));
vi.mock('../../services/recordings/blocks', () => ({resumeBlockInterview: (...args: unknown[]) => flow.resumeBlock(...args)}));

beforeEach(() => {
  vi.clearAllMocks();
  flow.role = 'student';
  flow.userId = 1;
  flow.routeId = '7';
  flow.profiles = [];
  flow.speechFrames = [];
  flow.load.mockReset();
  flow.load.mockImplementation(async () => flow.interview);
  flow.regenerate.mockResolvedValue(undefined);
  flow.recap.mockResolvedValue({interviewId: 7, turns: [], evaluationProcessing: {status: 'complete'}});
  flow.speech.isSubmittingUtterance = false;
  flow.speech.hasPendingUtterance = false;
  flow.route.state.justStarted = true;
  delete flow.route.state.resume;
  flow.resumeBlock.mockResolvedValue({resumeAttemptId: 'resume-attempt', offsetMs: 60_000,
    previousSegmentId: 'previous-segment', previousDurationMs: 60_000, pendingPatientMessageId: null});
  flow.recoverSegment.mockResolvedValue({status: 'partial'});
  flow.media.cameraState = 'ready';
  flow.fetchCount = 0;
  flow.loadError = false;
  flow.redirects = [];
  flow.interview.status = 'in_progress';
  flow.interview.lifecycle = undefined;
  flow.interview.startTime = '2026-11-02T12:00:00Z';
  flow.interview.messages = [];
  flow.interview.progressSummary = undefined;
  flow.interview.interviewMetadata = {};
  flow.interview.reviewAccess = undefined;
  flow.complete.mockResolvedValue({});
  flow.recording.status = 'recording';
  flow.recording.isCapturing = true;
  flow.recording.syncPending = false;
  flow.recording.stopForRecovery.mockResolvedValue(undefined);
  flow.recording.segmentId = 'synthetic-segment';
  flow.recording.sealForEnding.mockResolvedValue(true);
  flow.recording.canRestartWithCurrentGeometry.mockReturnValue(true);
  flow.recording.finalize.mockResolvedValue(true);
  flow.recording.pause.mockImplementation(() => {
    if (flow.recording.status === 'recording') flow.recording.status = 'paused';
  });
  flow.recording.resumeAudioGraph.mockResolvedValue(undefined);
  flow.summary.mockResolvedValue({});
  flow.send.mockResolvedValue({messages: [], newMessageIds: []});
  flow.start.mockImplementation(async () => {
    flow.interview.startTime = '2026-11-02T12:00:00Z';
    flow.interview.messages = [{id: 10, interviewId: 7, senderType: 'patient', content: 'Hello, nice to meet you.', createdAt: flow.interview.startTime}];
    return flow.interview;
  });
  document.body.innerHTML = '';
});
afterEach(() => {
 cleanup(); vi.useRealTimers();
});
const open = async () => {
  const view = render(<ClinicalChat mode="session" />);
  await screen.findByText('End');
  const accept = screen.queryByText('Accept instructions');
  if (accept) {
    fireEvent.click(accept);
    await waitFor(() => expect(screen.queryByText('Accept instructions')).toBeNull());
  }
  return view;
};

it('redirects a processing session to review without offering capture resumption', async () => {
  flow.interview.status = 'processing';
  flow.route.state.justStarted = false;
  render(<ClinicalChat mode="session" />);
  await waitFor(() => expect(flow.redirects).toContain('/interviews/7/review'));
  expect(screen.queryByText('clinicalChat.resumeSession.resume')).toBeNull();
});

it('holds a committed transcript during capture pause and sends it once capture recovers', async () => {
  const view = await open();
  act(() => flow.speechOptions.onUtteranceCommitted?.());
  flow.recording.syncPending = true;
  flow.recording.segmentId = '';
  view.rerender(<ClinicalChat mode="session" />);
  await act(async () => { await flow.speechOptions.onUtterance('Synthetic deferred transcript'); });
  expect(flow.send).not.toHaveBeenCalled();
  flow.recording.syncPending = false;
  flow.recording.segmentId = 'synthetic-segment';
  view.rerender(<ClinicalChat mode="session" />);
  await waitFor(() => expect(flow.send).toHaveBeenCalledTimes(1));
  expect(flow.send.mock.calls[0][1]).toBe('Synthetic deferred transcript');
});

it('waits for the last local fragment before reconciling a live block capture', async () => {
  flow.route.state.justStarted = false;
  flow.interview.lifecycle = {phase: 'active', canComplete: false, canRetryCompletion: false,
    canResumeCapture: true, recordingTransport: 'reusable_blocks_v1'};
  let stopped!: () => void;
  flow.recording.stopForRecovery.mockReturnValue(new Promise<void>((resolve) => { stopped = resolve; }));
  flow.resumeBlock.mockResolvedValue({resumeAttemptId: 'resume-attempt'});
  render(<ClinicalChat mode="session" />);
  fireEvent.click(await screen.findByText('clinicalChat.resumeSession.resume'));
  await waitFor(() => expect(flow.recording.stopForRecovery).toHaveBeenCalledTimes(1));
  expect(flow.resumeBlock).not.toHaveBeenCalled();
  await act(async () => stopped());
  await waitFor(() => expect(flow.resumeBlock).toHaveBeenCalledTimes(1));
});

it('does not play patient audio before capture has started successfully', async () => {
  flow.recording.status = 'failed';
  flow.recording.isCapturing = false;
  await open();
  expect(flow.transcript.playbackReady).toBe(false);
  flow.recording.isCapturing = true;
});

it('continues frozen media from the safe lifecycle even before automatic assessment is visible', async () => {
  flow.interview.lifecycle = {phase: 'capture_finalized', canComplete: true, canRetryCompletion: false,
    canResumeCapture: false, recordingTransport: 'reusable_blocks_v1'};
  flow.interview.reviewAccess = {canViewAssessments: false, assignmentId: null, selfAssessmentRequired: true};
  flow.complete.mockImplementation(async () => { flow.interview.status = 'processing'; return {}; });
  render(<ClinicalChat mode="review" />);
  fireEvent.click(await screen.findByText('common.retry'));
  await waitFor(() => expect(flow.complete).toHaveBeenCalledWith('7'));
  expect(flow.resumeRecording).not.toHaveBeenCalled();
});

it('starts the official clock and greeting only after accepting instructions', async () => {
  flow.interview.startTime = undefined;
  render(<ClinicalChat mode="session" />);
  const accept = await screen.findByText('Accept instructions');
  expect(flow.start).not.toHaveBeenCalled();
  expect(screen.queryByText('Regenerate')).toBeNull();
  expect(flow.captureOptions.enabled).toBe(false);
  expect(flow.speechOptions.disabled).toBe(true);
  expect(flow.transcript.playbackReady).toBe(false);
  expect(screen.getByLabelText('Elapsed time').textContent).toBe('0');
  fireEvent.click(accept);
  fireEvent.click(accept);
  await waitFor(() => expect(flow.captureOptions.enabled).toBe(true));
  expect(flow.start).toHaveBeenCalledExactlyOnceWith(7);
  expect(flow.recording.resumeAudioGraph).toHaveBeenCalledWith();
  expect(flow.transcript.messages?.[0].senderType).toBe('patient');
  expect(flow.transcript.playbackReady).toBe(true);
});

it('keeps instructions open when starting fails and allows retry', async () => {
  flow.interview.startTime = undefined;
  flow.start.mockRejectedValueOnce(new Error('Synthetic lost start response'));
  render(<ClinicalChat mode="session" />);
  fireEvent.click(await screen.findByText('Accept instructions'));
  expect((await screen.findByRole('alert')).textContent).toBe('Start failed');
  expect(flow.captureOptions.enabled).toBe(false);
  fireEvent.click(screen.getByText('Accept instructions'));
  await waitFor(() => expect(flow.captureOptions.enabled).toBe(true));
  expect(flow.start.mock.calls).toEqual([[7], [7]]);
});

it('plays the opening patient turn and waits before accepting student speech', async () => {
  flow.interview.messages = [{id: 10, interviewId: 7, senderType: 'patient',
    content: 'Hello, nice to meet you.', createdAt: flow.interview.startTime!}];
  await open();
  expect(flow.transcript.messages?.[0].messageMetadata?.isNew).toBe(true);
  expect(flow.transcript.playbackReady).toBe(true);
  expect(flow.speechOptions.paused).toBe(true);
  act(() => flow.transcript.onPatientTurnComplete?.(10));
  expect(flow.speechOptions.paused).toBe(false);
  expect(flow.send).not.toHaveBeenCalled();
});

it('places the timer in the conversation header and end controls inside its panel', async () => {
  await open();
  expect(screen.queryByRole('region', {name: 'Interview information'})).toBeNull();
  const conversation = screen.getByRole('region', {name: 'Interview conversation'});
  const panel = conversation.closest('.ui-panel')!;
  const end = screen.getByRole('button', {name: 'End'});
  expect(panel.contains(end)).toBe(true);
  expect(end.closest('footer')).toBeTruthy();
  expect(conversation.compareDocumentPosition(end)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  expect(conversation.querySelector('header')?.contains(screen.getByLabelText('Elapsed time'))).toBe(true);
});

it('opens review immediately after hypotheses are saved', async () => {
  const view = await open();
  fireEvent.click(screen.getByText('End'));
  flow.interview = {...flow.interview, status: 'processing', reviewAccess: {
    canViewAssessments: false, assignmentId: null, selfAssessmentRequired: true,
  }};
  await act(async () => flow.hypotheses.onCompleted?.({interview: {id: 7, status: 'processing'}, evaluationResults: []} as unknown as Parameters<NonNullable<typeof flow.hypotheses.onCompleted>>[0]));
  expect(flow.navigate).toHaveBeenCalledWith('/interviews/7/review', {replace: true});
  view.rerender(<ClinicalChat mode="review" />);
  await screen.findByRole('region', {name: 'Interview recap'});
  expect(flow.redirects).not.toContain('/interviews');
  flow.interview.reviewAccess = {canViewAssessments: true, assignmentId: null, selfAssessmentRequired: false};
  await act(async () => flow.humanRating.onSubmitted());
  expect(flow.review.evaluationData.interview.isOwner).toBe(true);
  expect(flow.review.isLoading).toBe(true);
  expect(screen.queryByText('clinicalChat.finalization.readyTitle')).toBeNull();
});

it('shows replay and the private self-rating form while automatic processing continues', async () => {
  flow.interview.status = 'processing';
  flow.interview.reviewAccess = {canViewAssessments: false, assignmentId: null, selfAssessmentRequired: true};
  render(<ClinicalChat mode="review" />);
  await screen.findByRole('region', {name: 'Interview information'});
  expect(screen.getByRole('region', {name: 'Interview recap'})).toBeTruthy();
  expect(screen.getByRole('region', {name: 'Private rating form'})).toBeTruthy();
  expect(flow.humanRating.selfInterviewId).toBe(7);
  expect(flow.humanRating.assignmentId).toBeUndefined();
  expect(flow.captureOptions.enabled).toBe(false);
  flow.interview.reviewAccess = {canViewAssessments: true, assignmentId: null, selfAssessmentRequired: false};
  await act(async () => flow.humanRating.onSubmitted());
  expect(screen.queryByRole('region', {name: 'Private rating form'})).toBeNull();
});

it('shows a recoverable initial load error instead of a blank view', async () => {
  flow.loadError = true;
  render(<ClinicalChat mode="session" />);
  expect((await screen.findByRole('alert')).textContent).toContain('clinicalChat.loadError');
  flow.loadError = false;
  fireEvent.click(screen.getByText('common.retry'));
  await screen.findByText('End');
});

it('keeps the same request key and speech timing after a lost message acknowledgement', async () => {
  flow.send.mockRejectedValueOnce(new Error('Synthetic lost acknowledgement'));
  await open();
  const timing = {startMs: 100, endMs: 500};
  await act(async () => flow.speechOptions.onUtterance('Synthetic retry', timing));
  expect(flow.speechOptions.paused).toBe(true);
  flow.send.mockResolvedValueOnce({messages: [{id: 9, content: 'Synthetic retry', senderType: 'user', createdAt: '', interviewId: 7}], newMessageIds: [9]});
  fireEvent.click(screen.getByText('common.retry'));
  await waitFor(() => expect(flow.send).toHaveBeenCalledTimes(2));
  expect(flow.send.mock.calls[0][2]).toBeTruthy();
  expect(flow.send.mock.calls[1]).toEqual(flow.send.mock.calls[0]);
  expect(flow.recording.recordStudentTurn).toHaveBeenCalledWith(9, 0, 'Synthetic retry', timing);
  expect(flow.speechOptions.paused).toBe(false);
});

it('correlates spoken input and first playback to the same request', async () => {
  const measure = vi.fn();
  vi.stubGlobal('performance', {now: performance.now.bind(performance), measure});
  try {
    await open();
    flow.send.mockResolvedValueOnce({
      messages: [{id: 10, content: 'Synthetic reply', senderType: 'patient', createdAt: '', interviewId: 7}],
      newMessageIds: [10],
    });
    act(() => flow.speechOptions.onUtteranceCommitted?.());
    await act(async () => flow.speechOptions.onUtterance('Synthetic question'));
    const requestId = flow.send.mock.calls[0][2];
    flow.transcript.onPatientTurnStart?.(99, 0, 'Older audio');
    expect(measure).not.toHaveBeenCalledWith('patient-response:total-to-playing', expect.anything());
    flow.transcript.onPatientTurnStart?.(10, 0, 'Synthetic reply');
    for (const stage of ['transcription', 'reply', 'audio-start', 'total-to-playing']) {
      expect(measure).toHaveBeenCalledWith('patient-response:' + stage, expect.objectContaining({
        detail: {requestId},
      }));
    }
    expect(flow.recording.beginPatientTurn).toHaveBeenCalledWith(10);
  } finally {
    vi.unstubAllGlobals();
  }
});

it('retries technical completion from review without reopening capture', async () => {
  flow.interview.status = 'interrupted';
  flow.interview.interviewMetadata = {completionProcessing: {status: 'failed'}};
  flow.complete.mockImplementation(async () => {
    flow.interview.status = 'processing';
  });
  render(<ClinicalChat mode="review" />);
  fireEvent.click(await screen.findByText('common.retry'));
  await screen.findByText('clinicalChat.processing');
  expect(flow.complete).toHaveBeenCalledWith('7');
  expect(flow.captureOptions.enabled).toBe(false);
  expect(flow.recording.resume).not.toHaveBeenCalled();
});

it('blocks clicks and keyboard handlers while speech is being submitted', async () => {
  flow.speech.isSubmittingUtterance = true;
  await open();
  expect(flow.toolbar.endDisabled).toBe(true);
  act(() => flow.toolbar.onEndInterview());
  expect(flow.recording.sealForEnding).not.toHaveBeenCalled();
});

it('discards an unsent intervention and seals once before allowing cancellation', async () => {
  flow.speech.hasPendingUtterance = true;
  await open();
  expect(flow.toolbar.endDisabled).toBe(false);
  await act(async () => {
 flow.toolbar.onEndInterview(); flow.toolbar.onEndInterview();
});
  expect(flow.speech.stop).toHaveBeenCalled();
  expect(flow.recording.discardStudentTurn).toHaveBeenCalledOnce();
  expect(flow.recording.sealForEnding).toHaveBeenCalledOnce();
  expect(flow.hypotheses.canCancel).toBe(true);
  await act(async () => { await flow.hypotheses.onCancel(); });
  expect(flow.recording.restartAfterCancel).toHaveBeenCalledOnce();
  expect(screen.queryByTestId('hypotheses')).toBeNull();
});

it('accepts a close click immediately after an utterance commits', async () => {
  await open();
  act(() => {
    flow.speechOptions.onUtteranceCommitted();
    flow.toolbar.onEndInterview();
  });
  expect(flow.recording.pause).not.toHaveBeenCalled();
});

it('blocks finalization during generation', async () => {
  flow.send.mockReturnValue(new Promise(() => undefined));
  await open();
  act(() => {
    void flow.speechOptions.onUtterance('Synthetic accepted message');
  });
  await waitFor(() => expect(flow.send).toHaveBeenCalledOnce());
  expect(flow.summary).not.toHaveBeenCalled();
  expect(flow.toolbar.endDisabled).toBe(true);
  act(() => flow.toolbar.onEndInterview());
  expect(flow.recording.sealForEnding).not.toHaveBeenCalled();
});

it('accepts only one send while asynchronous audio setup is pending', async () => {
  let ready!: () => void;
  flow.recording.resumeAudioGraph.mockReturnValue(
    new Promise<void>((resolve) => {
      ready = resolve;
    }),
  );
  await open();
  await act(async () => {
    void flow.speechOptions.onUtterance('First synthetic message');
    void flow.speechOptions.onUtterance('Duplicate event');
    ready();
  });
  expect(flow.send).toHaveBeenCalledOnce();
});

it('keeps completion open until sealing and preservation succeed', async () => {
  flow.recording.sealForEnding.mockResolvedValue(false);
  await open();
  fireEvent.click(screen.getByText('End'));
  expect(screen.queryByTestId('hypotheses')).not.toBeNull();
  await waitFor(() => expect(flow.hypotheses.preparingCapture).toBe(false));
  await act(async () => { await flow.hypotheses.onCancel(); });
  expect(flow.recording.restartAfterCancel).not.toHaveBeenCalled();
  expect(screen.queryByTestId('hypotheses')).not.toBeNull();
});

it('consumes the fresh-start navigation flag while keeping the current capture active', async () => {
  await open();
  expect(flow.navigate).toHaveBeenCalledWith(flow.route.pathname, {
    replace: true,
    state: {justStarted: false},
  });
  expect(flow.captureOptions.enabled).toBe(true);
});

it('keeps a re-entered capture stopped when device state changes', async () => {
  flow.route.state.justStarted = false;
  const {rerender} = render(<ClinicalChat mode="session" />);
  await screen.findByRole('button', {name: 'clinicalChat.resumeSession.forceTermination'});
  expect(screen.queryByText('Regenerate')).toBeNull();
  expect(screen.queryByText('End')).toBeNull();
  expect(screen.queryByText('clinicalChat.resumeSession.resume')).not.toBeNull();
  expect(flow.captureOptions.enabled).toBe(false);
  const previous = flow.fetchCount;
  flow.media.cameraState = 'unavailable';
  rerender(<ClinicalChat mode="session" />);
  expect(flow.fetchCount).toBe(previous);
  expect(flow.captureOptions.enabled).toBe(false);
});

it('closes a re-entered interview using the server record without finalizing a new capture', async () => {
  flow.route.state.justStarted = false;
  flow.recording.status = 'idle';
  flow.recording.finalize.mockResolvedValue(false);
  flow.interrupt.mockResolvedValue(undefined);
  render(<ClinicalChat mode="session" />);
  fireEvent.click(await screen.findByRole('button', {name: 'clinicalChat.resumeSession.forceTermination'}));
  await waitFor(() => expect(flow.navigate).toHaveBeenCalledWith('/interviews', {replace: true}));
  expect(flow.interrupt).toHaveBeenCalledExactlyOnceWith('7', {resumeAttemptId: 'resume-attempt', signal: expect.any(AbortSignal)});
  expect(flow.recording.finalize).not.toHaveBeenCalled();
});

it('resumes the same interview through calibration after recovering its previous segment', async () => {
  flow.route.state.justStarted = false;
  render(<ClinicalChat mode="session" />);
  fireEvent.click(await screen.findByRole('button', {name: 'clinicalChat.resumeSession.resume'}));
  await waitFor(() => expect(flow.navigate).toHaveBeenCalledWith('/interviews/calibration', {
    replace: true, state: {draftInterviewId: 7, resume: expect.objectContaining({offsetMs: 60_000})},
  }));
  expect(flow.recording.stopForRecovery).toHaveBeenCalledBefore(flow.resumeBlock);
  expect(flow.resumeBlock).toHaveBeenCalledWith(7, expect.any(String));
  expect(flow.captureOptions.enabled).toBe(false);
  expect(flow.start).not.toHaveBeenCalled();
});

it('allows forced interruption after reload even when local media cannot be read', async () => {
  flow.route.state.justStarted = false;
  flow.recoverSegment.mockRejectedValue(new Error('Local files unavailable'));
  flow.interrupt.mockResolvedValue(undefined);
  render(<ClinicalChat mode="session" />);
  fireEvent.click(await screen.findByRole('button', {name: 'clinicalChat.resumeSession.forceTermination'}));
  await waitFor(() => expect(flow.interrupt).toHaveBeenCalledExactlyOnceWith('7', {resumeAttemptId: 'resume-attempt', signal: expect.any(AbortSignal)}));
  expect(flow.recording.finalize).not.toHaveBeenCalled();
  expect(flow.recoverSegment).not.toHaveBeenCalled();
});

it('retries recovery with the same resume request after a lost upload response', async () => {
  flow.route.state.justStarted = false;
  flow.resumeBlock.mockRejectedValueOnce(new Error('Lost upload response')).mockResolvedValueOnce({resumeAttemptId: 'resume-attempt'});
  render(<ClinicalChat mode="session" />);
  fireEvent.click(await screen.findByRole('button', {name: 'clinicalChat.resumeSession.resume'}));
  await screen.findByRole('alert');
  expect(flow.navigate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'clinicalChat.resumeSession.resume'}));
  await waitFor(() => expect(flow.navigate).toHaveBeenCalledWith('/interviews/calibration', expect.any(Object)));
  expect(flow.resumeBlock.mock.calls[0]).toEqual(flow.resumeBlock.mock.calls[1]);
});

it('replays only the pending server patient message after recalibration', async () => {
  flow.route.state.resume = {resumeAttemptId: 'resume-attempt', offsetMs: 60_000,
    pendingPatientMessageId: 12};
  flow.interview.messages = [
    {id: 10, interviewId: 7, senderType: 'patient', content: 'Greeting', createdAt: ''},
    {id: 11, interviewId: 7, senderType: 'user', content: 'Question', createdAt: ''},
    {id: 12, interviewId: 7, senderType: 'patient', content: 'Saved reply', createdAt: ''},
  ];
  await open();
  expect(flow.transcript.messages?.filter((message) => message.messageMetadata?.isNew).map((message) => message.id)).toEqual([12]);
  expect(flow.speechOptions.paused).toBe(true);
  expect(flow.toolbar.endDisabled).toBe(true);
  act(() => flow.transcript.onPatientTurnComplete?.(12, 'written'));
  expect(flow.recording.recordWrittenPatientTurn).toHaveBeenCalledWith(12);
  expect(flow.toolbar.endDisabled).toBe(false);
  expect(flow.send).not.toHaveBeenCalled();
});

it('blocks finalization during patient playback and enables it only after delivery', async () => {
  await open();
  act(() => flow.transcript.onPatientSpeakingChange(true));
  fireEvent.click(screen.getByText('End'));
  expect(screen.queryByTestId('hypotheses')).toBeNull();
  act(() => flow.transcript.onPatientSpeakingChange(false));
  await act(async () => fireEvent.click(screen.getByText('End')));
  expect(screen.queryByTestId('hypotheses')).not.toBeNull();
});

it('blocks a completion callback in the same event as patient playback starts', async () => {
  await open();
  act(() => {
    flow.transcript.onPatientSpeakingChange(true);
    flow.transcript.onPatientTurnStart?.(12, 0, 'Saved reply');
    flow.toolbar.onEndInterview();
  });
  expect(flow.recording.sealForEnding).not.toHaveBeenCalled();
});

it('keeps cancellation available without an interruption action in the hypotheses dialog', async () => {
  flow.recording.status = 'failed';
  flow.recording.sealForEnding.mockResolvedValue(false);
  await open();
  fireEvent.click(screen.getByText('End'));
  expect(flow.hypotheses.canCancel).toBe(true);
  expect(flow.hypotheses.onInterrupt).toBeUndefined();
});

it('loads the saved progress summary in review without generating it again', async () => {
  flow.interview.status = 'completed';
  flow.interview.progressSummary = {summaryText: 'Saved patient summary'};
  render(<ClinicalChat mode="review" />);
  expect(await screen.findByText('Saved patient summary')).toBeDefined();
  const information = screen.getByRole('region', {name: 'Interview information'});
  expect(within(information).getByRole('region', {name: 'Interview recap'})).toBeDefined();
  expect(within(information).queryByRole('button', {name: 'Regenerate'})).toBeNull();
  expect(screen.getByRole('button', {name: 'Regenerate'})).toBeDefined();
  expect(flow.summary).not.toHaveBeenCalled();
});

it('serializes review regeneration and reloads only after terminal evaluation', async () => {
  flow.role = 'superuser';
  flow.interview.status = 'completed';
  render(<ClinicalChat mode="review" />);
  await screen.findByText('Regenerate');
  vi.useFakeTimers();
  await act(async () => {
 flow.review.onRegenerate?.(); flow.review.onRegenerate?.();
});
  expect(flow.regenerate).toHaveBeenCalledOnce();
  expect(flow.review.isRegenerating).toBe(true);
  const loaded = flow.fetchCount;
  await act(async () => {
 await vi.advanceTimersByTimeAsync(3000);
});
  expect(flow.recap).toHaveBeenCalledWith(7, expect.any(AbortSignal));
  expect(flow.fetchCount).toBe(loaded + 1);
  expect(flow.review.isRegenerating).toBe(false);
  expect(flow.captureOptions.enabled).toBe(false);
});

it('stops review polling after unmount without reopening capture', async () => {
  flow.role = 'superuser';
  flow.interview.status = 'completed';
  const view = render(<ClinicalChat mode="review" />);
  await screen.findByText('Regenerate');
  vi.useFakeTimers();
  await act(async () => {
 flow.review.onRegenerate?.();
});

  view.unmount();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(flow.recap).not.toHaveBeenCalled();
  expect(flow.captureOptions.enabled).toBe(false);
});

it.each(['interview', 'account'])('never renders previous profile during a change of %s identity', async (identity) => {
  flow.interview.status = 'completed';
  flow.interview.progressSummary = {summaryText: 'Previous private profile'};
  const view = render(<ClinicalChat mode="review" />);
  await screen.findByText('Previous private profile');
  let resolve!: (value: typeof flow.interview) => void;
  flow.load.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
  flow.profiles = [];
  if (identity === 'interview') flow.routeId = '8';
  else flow.userId = 2;
  view.rerender(<ClinicalChat mode="review" />);
  expect(flow.profiles.some((profile) => profile.summary === 'Previous private profile')).toBe(false);
  await act(async () => resolve({...flow.interview, id: Number(flow.routeId), progressSummary: {summaryText: 'Current profile'}}));
  await screen.findByText('Current profile');
});

it('waits for a slow detail poll before scheduling the next request and retains confirmed content', async () => {
  flow.interview.status = 'processing';
  flow.interview.progressSummary = {summaryText: 'Confirmed profile'};
  vi.useFakeTimers();
  await act(async () => { render(<ClinicalChat mode="review" />); });
  expect(screen.queryByText('Confirmed profile')).not.toBeNull();
  let resolve!: (value: typeof flow.interview) => void;
  flow.load.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
  await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
  expect(flow.fetchCount).toBe(2);
  expect(screen.queryByText('Confirmed profile')).not.toBeNull();
  await act(async () => resolve({...flow.interview, status: 'completed', progressSummary: {summaryText: 'Finished profile'}}));
  expect(screen.queryByText('Finished profile')).not.toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(flow.fetchCount).toBe(2);
});

it('pauses speech and submission in the first render of a capture pause', async () => {
  const view = await open();
  flow.speechFrames = [];
  flow.recording.syncPending = true;
  view.rerender(<ClinicalChat mode="session" />);
  expect(flow.speechFrames.every((frame) => !frame.pending || frame.paused)).toBe(true);
  expect(flow.toolbar.endDisabled).toBe(true);
});

