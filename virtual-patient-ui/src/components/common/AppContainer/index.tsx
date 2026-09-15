import {useEffect, useState} from 'react';
import {Outlet, useLocation, matchPath} from 'react-router-dom';
import {Header} from '../Header';
import {Footer} from '../Footer';
import {TokenExpiredScreen} from '../../TokenExpiredScreen';
import {useAuthError} from '../../../hooks/useAuthError';
import {ROUTES} from '../../../utils/routes';
import {InterviewMediaProvider} from '../../../contexts/InterviewMediaContext';

export type AppContainerOutletContext = {
  setClinicalSimulationActive: (active: boolean) => void;
};

export const AppContainer = () => {
  const { isTokenExpired } = useAuthError();
  const {pathname} = useLocation();
  const legacyCalibrationMatch = matchPath(ROUTES.interviewCalibration, pathname);
  const preInterviewCalibrationMatch = matchPath(ROUTES.calibration, pathname);
  const calibrationMatch = legacyCalibrationMatch || preInterviewCalibrationMatch;
  const sessionMatch = matchPath(ROUTES.interviewSession, pathname);
  const reviewMatch = matchPath(ROUTES.interviewReview, pathname);
  const interviewId = legacyCalibrationMatch?.params.interviewId || sessionMatch?.params.interviewId;
  const isClinicalChat = Boolean(sessionMatch || reviewMatch);
  const isInterviewFlow = Boolean(calibrationMatch || sessionMatch || reviewMatch);
  const [clinicalSimulationActive, setClinicalSimulationActive] = useState(false);

  useEffect(() => {
    if (!isClinicalChat) setClinicalSimulationActive(false);
  }, [isClinicalChat]);

  if (isTokenExpired) {
    return <TokenExpiredScreen />;
  }

  return (
    <InterviewMediaProvider interviewId={interviewId}>
      <div
        className={`flex w-full min-w-0 flex-col overflow-hidden bg-neutral-100 ${
          isInterviewFlow ? 'h-dvh' : 'min-h-screen'
        }`}
      >
        {!calibrationMatch && <Header clinicalSimulationActive={clinicalSimulationActive} />}
        <main
          className={`flex w-full min-w-0 flex-1 flex-col items-center ${
            isClinicalChat
              ? 'min-h-0 overflow-hidden px-3 py-3 sm:px-4 lg:px-6 lg:py-4'
              : calibrationMatch
                ? 'min-h-0 overflow-auto px-3 py-3 sm:px-4 lg:px-6 lg:py-4'
              : 'mb-6 px-4 py-6 sm:px-6 md:py-8 lg:px-20 lg:pt-10'
          }`}
        >
          <div className="flex h-full min-h-0 w-full min-w-0 flex-col items-start">
            <Outlet context={{setClinicalSimulationActive}} />
          </div>
        </main>
        {!isInterviewFlow && <Footer />}
      </div>
    </InterviewMediaProvider>
  );
};
