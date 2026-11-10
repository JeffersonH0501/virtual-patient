export const ROUTES = {
  home: '/',
  welcome: '/welcome',
  clinicalCases: '/cases',
  patientPreview: '/interviews/session-preview',
  calibration: '/interviews/calibration',
  interviews: '/interviews',
  interviewSession: '/interviews/:interviewId/session',
  interviewReview: '/interviews/:interviewId/review',
  users: '/users',
  perceptionSurvey: '/perception-survey',
};

export const interviewPath = (interviewId: string | number, stage: 'session' | 'review') =>
  `${ROUTES.interviews}/${encodeURIComponent(String(interviewId))}/${stage}`;


export type NavigationSection = 'cases' | 'interviews' | 'users' | 'perception';

/** Resolve one visible navigation tab, including interview detail routes. */
export const getNavigationSection = (pathname: string, role?: string): NavigationSection => {
  if (pathname === ROUTES.perceptionSurvey && role !== 'superuser') return 'perception';
  if (pathname === ROUTES.calibration || pathname === ROUTES.patientPreview) return 'cases';
  if (pathname === ROUTES.clinicalCases || pathname.startsWith(ROUTES.clinicalCases + '/')) return 'cases';
  if (pathname === ROUTES.users && role === 'superuser') return 'users';
  if (pathname === ROUTES.interviews || pathname.startsWith(ROUTES.interviews + '/')) {
    return 'interviews';
  }
  return role === 'superuser' ? 'interviews' : 'cases';
};

/** Case configuration carried to calibration before creating an interview draft. */
export type CalibrationRouteState = {
  calibrationTest?: boolean;
  gazeTest?: boolean;
  clinicalCaseId: number;
  clinicalCaseTitle?: string;
  gender?: string;
  personalityId?: number;
  patientResponseLanguage: 'en' | 'es';
};

export type InterviewResumeState = {
  resumeAttemptId: string;
  offsetMs: number;
  pendingPatientMessageId?: number | null;
};
