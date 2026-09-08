import {FC} from 'react';
import {BrowserRouter as Router, Routes, Route, Navigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {useUser} from './hooks/useUser';
import {Login} from './components/Login';
import {ClinicalCases} from './components/ClinicalCases';
import {ROUTES} from './utils/routes';
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

  if (isLoading) {
    return <div role="status">{t('common.loading')}</div>;
  }

  return <Navigate to={user ? ROUTES.clinicalCases : ROUTES.signIn} replace />;
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
