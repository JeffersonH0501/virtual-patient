export const ROUTES = {
  home: '/',
  signIn: '/signin',
  resetPassword: '/reset-password',
  signUp: '/signup',
  clinicalCases: '/cases',
  clinicalSession: '/session',
  createCase: '/cases/create',
  editCase: '/cases/:caseId/edit',
  // Pre-interview calibration. The interview row is only created once the
  // simulation actually starts, so this route carries the case configuration
  // via location.state instead of an interview id.
  calibration: '/cases/calibration',
  interviews: '/interviews',
  interviewCalibration: '/interviews/:interviewId/calibration',
  interviewSession: '/interviews/:interviewId/session',
  interviewReview: '/interviews/:interviewId/review',
  students: '/students',
};

export const interviewPath = (interviewId: string | number, stage: 'calibration' | 'session' | 'review') =>
  `${ROUTES.interviews}/${encodeURIComponent(String(interviewId))}/${stage}`;

/**
 * Case configuration carried to the calibration route via location.state. The
 * interview is created only when the simulation actually starts, so this config
 * lives on the client until then.
 */
export type CalibrationRouteState = {
  clinicalCaseId: number;
  clinicalCaseTitle?: string;
  gender?: string;
  personalityId?: number;
  patientResponseLanguage: 'en' | 'es';
};
