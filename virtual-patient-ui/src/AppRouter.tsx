import {FC, useEffect, useState} from 'react';
import {BrowserRouter as Router, Routes, Route, Navigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {useUser} from './hooks/useUser';
import {Login} from './components/Login';
import {ClinicalCases} from './components/ClinicalCases';
import {ROUTES, interviewPath} from './utils/routes';
import {getActiveInterview} from './services/interviews';
import {MedicalConsultationForm} from './components/MedicalConsultationForm';
import {AppContainer} from './components/common';
import {ClinicalChat} from './components/ClinicalChat';
import {Chats} from './components/Chats';
import {InterviewCalibration} from './components/InterviewCalibration';
import {SignUp} from './components/SignUp';
import {ResetPassword} from './components/ResetPassword';
import {Students} from './components/Students';

const EntryRedirect: FC = () => {
  const {user, isLoading} = useUser();
  const {t} = useTranslation();
  // null: not resolved yet; string: destination route.
  const [destination, setDestination] = useState<string | null>(null);

  useEffect(() => {
    if (isLoading) return;
    if (!user) {
      setDestination(ROUTES.signIn);
      return;
    }
    // The superuser never runs interviews; send it straight to its home.
    if (user.role === 'superuser') {
      setDestination(ROUTES.students);
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
            : ROUTES.clinicalCases,
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
      <Route path={ROUTES.signIn} element={<Login />} />
      <Route path={ROUTES.signUp} element={<SignUp />} />
      <Route path={ROUTES.resetPassword} element={<ResetPassword />} />
      <Route element={<AppContainer />}>
        <Route path={ROUTES.clinicalCases} element={<ClinicalCases />} />
        <Route path={ROUTES.calibration} element={<InterviewCalibration />} />
        <Route path={ROUTES.createCase} element={<MedicalConsultationForm mode="create" />} />
        <Route path={ROUTES.editCase} element={<MedicalConsultationForm mode="edit" />} />
        <Route path={ROUTES.interviewCalibration} element={<InterviewCalibration />} />
        <Route path={ROUTES.interviewSession} element={<ClinicalChat key="session" mode="session" />} />
        <Route path={ROUTES.interviewReview} element={<ClinicalChat key="review" mode="review" />} />
        <Route path={ROUTES.interviews} element={<Chats />} />
        <Route path={ROUTES.students} element={<Students />} />
      </Route>
    </Routes>
  </Router>
);
