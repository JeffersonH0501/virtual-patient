import {ConversationTable} from './ConversationTable';
import {PersonalStatisticsCards} from './PersonalStatisticsCards';
import {Navigate} from 'react-router-dom';
import {useUser} from '../../hooks';
import {ROUTES} from '../../utils/routes';

export const Chats = () => {
  const {user} = useUser();

  if (user?.role === 'superuser') {
    return <Navigate to={ROUTES.students} replace />;
  }

  return (
    <main className="mx-auto flex w-full max-w-content flex-col gap-2 px-4 py-0">
      <PersonalStatisticsCards />
      <ConversationTable />
    </main>
  );
};
