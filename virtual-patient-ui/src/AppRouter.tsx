import {FC, lazy, useEffect, useState} from 'react';
import {BrowserRouter as Router, Routes, Route, Navigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {useUser} from './hooks/useUser';
import {AuthLayout} from './components/Auth/AuthLayout';
import {ROUTES, interviewPath} from './utils/routes';
import {getActiveInterview} from './services/interviews';
import {AppContainer} from './components/common';

const ClinicalCases = lazy(() => import('./components/ClinicalCases').then((module) => ({default: module.ClinicalCases})));
const Chats = lazy(() => import('./components/Chats').then((module) => ({default: module.Chats})));
const Users = lazy(() => import('./components/Users').then((module) => ({default: module.Users})));
const PerceptionSurvey = lazy(() => import('./components/PerceptionSurvey').then((module) => ({default: module.PerceptionSurvey})));
const InterviewCalibration = lazy(() => import('./components/InterviewCalibration').then((module) => ({default: module.InterviewCalibration})));
const ClinicalChat = lazy(() => import('./components/ClinicalChat').then((module) => ({default: module.ClinicalChat})));


const EntryRedirect: FC = () => {
  const {user, isLoading} = useUser();
  const {t} = useTranslation();
  // null: not resolved yet; string: destination route.
  const [destination, setDestination] = useState<string | null>(null);

  useEffect(() => {
    if (isLoading) return;
    if (!user) {
      setDestination(ROUTES.welcome);
      return;
    }
    if (user.role === 'admin') {
      setDestination(ROUTES.clinicalCases);
      return;
    }

    let active = true;
    // On re-entry, resume an unfinished session if one exists. The session view
    // offers to resume it or force its termination.
    void getActiveInterview()
      .then((activeInterview) => {
        if (!active) return;
        setDestination(
          activeInterview
            ? interviewPath(activeInterview.id, 'session')
            : ROUTES.interviews,
        );
      })
      .catch(() => {
        if (active) setDestination(ROUTES.clinicalCases);
      });
    return () => {
      active = false;
    };
  }, [isLoading, user]);

  if (isLoading || destination === null) {
    return <div role="status">{t('common.loading')}</div>;
  }

  return <Navigate to={destination} replace />;
};

export const AppRouter: FC = () => (
  <Router>
    <Routes>
      <Route path={ROUTES.home} element={<EntryRedirect />} />
      <Route path={ROUTES.welcome} element={<AuthLayout />} />
      <Route element={<AppContainer />}>
        <Route path={ROUTES.clinicalCases} element={<ClinicalCases />} />
        <Route path={ROUTES.calibration} element={<InterviewCalibration />} />
        <Route path={ROUTES.interviewSession} element={<ClinicalChat key="session" mode="session" />} />
        <Route path={ROUTES.interviewReview} element={<ClinicalChat key="review" mode="review" />} />
        <Route path={ROUTES.interviews} element={<Chats />} />
        <Route path={ROUTES.users} element={<Users />} />
        <Route path={ROUTES.perceptionSurvey} element={<PerceptionSurvey />} />
      </Route>
      <Route path="*" element={<Navigate to={ROUTES.home} replace />} />
    </Routes>
  </Router>
);
