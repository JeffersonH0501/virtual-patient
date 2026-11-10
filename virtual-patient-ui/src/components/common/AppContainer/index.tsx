import {useTranslation} from 'react-i18next';
import {Suspense, useEffect, useRef, useState} from 'react';
import {Navigate, Outlet, useLocation, matchPath, useNavigate} from 'react-router-dom';
import {Header} from '../Header';
import {Footer} from '../Footer';
import {TokenExpiredScreen} from '../../TokenExpiredScreen';
import {useAuthError} from '../../../hooks/useAuthError';
import {interviewPath, ROUTES} from '../../../utils/routes';
import {InterviewMediaProvider} from '../../../contexts/InterviewMediaContext';
import {getActiveInterview} from '../../../services/interviews';
import {useUser} from '../../../hooks/useUser';
import {MotionContent} from '../Motion';
import {SessionListsProvider} from '../../../contexts/SessionLists';
import {InterviewContentLoading} from '../../ClinicalChat/InterviewContentLoading';

export const AppContainer = () => {
  const {user} = useUser();
  return <AccountAppContainer key={`${user?.id}:${user?.role}:${user?.organizationId}`} />;
};

const AccountAppContainer = () => {
  const {t} = useTranslation();
  const {isTokenExpired} = useAuthError();
  const {user, isLoading: isUserLoading} = useUser();
  const navigate = useNavigate();
  const navigateRef = useRef(navigate);
  const mainRef = useRef<HTMLElement>(null);
  useEffect(() => {
    navigateRef.current = navigate;
  }, [navigate]);
  const {pathname, state} = useLocation();
  useEffect(() => {
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [pathname]);
  const calibrationMatch = matchPath(ROUTES.calibration, pathname);
  const sessionMatch = matchPath(ROUTES.interviewSession, pathname);
  const reviewMatch = matchPath(ROUTES.interviewReview, pathname);
  const isPatientPreview = pathname === ROUTES.patientPreview;
  const interviewId = sessionMatch?.params.interviewId;
  const isClinicalChat = Boolean(sessionMatch || reviewMatch || isPatientPreview);
  const isInterviewFlow = Boolean(calibrationMatch || isClinicalChat);
  const activeFlowPath = calibrationMatch || sessionMatch ? pathname : null;
  const resumeInterviewId = calibrationMatch && state?.resume?.resumeAttemptId
    ? state.draftInterviewId : undefined;
  const userId = user?.id;
  const userRole = user?.role;
  const [checkingActiveInterview, setCheckingActiveInterview] = useState(true);
  const initialCheckDone = useRef(false);

  useEffect(() => {
    if (isUserLoading) return;
    if (userId == null || (userRole !== 'student' && userRole !== 'teacher') || isTokenExpired) {
      setCheckingActiveInterview(false);
      return;
    }

    let current = true;
    if (!initialCheckDone.current) setCheckingActiveInterview(true);
    void getActiveInterview()
      .then((activeInterview) => {
        if (!current) return;
        if (
          activeInterview?.status === 'in_progress' &&
          activeInterview.startTime &&
          String(sessionMatch?.params.interviewId) !== String(activeInterview.id) &&
          String(resumeInterviewId) !== String(activeInterview.id)
        ) {
          navigateRef.current(interviewPath(activeInterview.id, 'session'), {replace: true});
          return;
        }
        initialCheckDone.current = true;
        setCheckingActiveInterview(false);
      })
      .catch(() => {
        if (current) {
          initialCheckDone.current = true;
          setCheckingActiveInterview(false);
        }
      });
    return () => {
      current = false;
    };
  }, [activeFlowPath, isTokenExpired, isUserLoading, resumeInterviewId, sessionMatch?.params.interviewId, userId, userRole]);

  if (isTokenExpired) {
    return <TokenExpiredScreen />;
  }

  if (!isUserLoading && !user) {
    return <Navigate to={ROUTES.welcome} replace />;
  }

  if (isUserLoading || checkingActiveInterview) {
    if (isClinicalChat || pathname === ROUTES.interviews) return <InterviewContentLoading />;
    return (
      <div className="ui-empty-state" role="status">
        {t('common.loading')}
      </div>
    );
  }

  return (
    <SessionListsProvider user={user} interviewFlow={Boolean(sessionMatch || reviewMatch)}>
      <InterviewMediaProvider interviewId={interviewId}>
        <div
          data-ui-motion="app"
          className={`app-shell flex w-full min-w-0 flex-col overflow-hidden ${calibrationMatch ? 'bg-neutral-950' : 'bg-neutral-100'}`}
        >
          <a className="ui-skip-link" href="#main-content">
            {t('common.skipToContent')}
          </a>
          {!calibrationMatch && !sessionMatch && !isPatientPreview && <Header />}
          <main
            ref={mainRef}
            id="main-content"
            tabIndex={-1}
            className={`flex min-h-0 w-full min-w-0 flex-1 flex-col items-center ${isInterviewFlow ? 'ui-viewport' : ''} ${
              isClinicalChat && !reviewMatch
                ? 'overflow-hidden'
                : calibrationMatch
                  ? 'overflow-auto'
                  : 'overflow-y-auto'
            }`}
          >
            <MotionContent
              changeKey={pathname === ROUTES.interviews || pathname === ROUTES.users ? undefined : pathname}
              className={`flex w-full min-w-0 flex-col items-start ${reviewMatch ? 'review-viewport-content min-h-0 shrink-0' : isInterviewFlow ? 'min-h-0 h-full' : 'ui-viewport flex-1 shrink-0'}`}
            >
              <Suspense fallback={isClinicalChat || pathname === ROUTES.interviews
                ? <InterviewContentLoading /> : <div className="ui-empty-state" role="status">{t('common.loading')}</div>}>
                <Outlet />
              </Suspense>
            </MotionContent>
            {!isInterviewFlow && <Footer />}
          </main>
        </div>
      </InterviewMediaProvider>
    </SessionListsProvider>
  );
};
