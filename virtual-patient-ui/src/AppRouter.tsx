import {FC} from 'react';
import {BrowserRouter as Router, Routes, Route} from 'react-router-dom';
import {Login} from './components/Login';
import {ClinicalCases} from './components/ClinicalCases';
import {ROUTES} from './utils/routes';
import {MedicalConsultationForm} from './components/MedicalConsultationForm';
import {AppContainer} from './components/common';
import {ClinicalChat} from './components/ClinicalChat';
import {Chats} from './components/Chats';
import {ChatDetail} from './components/Chats/ChatDetail';
import {SignUp} from './components/SignUp';
import {Students} from './components/Students';

export const AppRouter: FC = () => (
  <Router>
    <Routes>
      <Route path={ROUTES.home} element={<Login />} />
      <Route path={ROUTES.signUp} element={<SignUp />} />
      <Route element={<AppContainer />}>
        <Route path={ROUTES.clinicalCases} element={<ClinicalCases />} />
        <Route path={ROUTES.createCase} element={<MedicalConsultationForm mode="create" />} />
        <Route path={ROUTES.editCase} element={<MedicalConsultationForm mode="edit" />} />
        <Route path={ROUTES.clinicalChat + '/:interviewId'} element={<ClinicalChat />} />
        <Route path={ROUTES.conversations} element={<Chats />} />
        <Route path={ROUTES.conversationDetail} element={<ChatDetail />} />
        <Route path={ROUTES.students} element={<Students />} />
      </Route>
    </Routes>
  </Router>
);
