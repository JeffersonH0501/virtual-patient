export const ROUTES = {
  home: '/',
  signIn: '/signin',
  resetPassword: '/reset-password',
  signUp: '/signup',
  clinicalCases: '/cases',
  clinicalSession: '/session',
  createCase: '/cases/create',
  editCase: '/cases/:caseId/edit',
  interviews: '/interviews',
  interviewCalibration: '/interviews/:interviewId/calibration',
  interviewSession: '/interviews/:interviewId/session',
  interviewReview: '/interviews/:interviewId/review',
  students: '/students',
};

export const interviewPath = (interviewId: string | number, stage: 'calibration' | 'session' | 'review') =>
  `${ROUTES.interviews}/${encodeURIComponent(String(interviewId))}/${stage}`;
