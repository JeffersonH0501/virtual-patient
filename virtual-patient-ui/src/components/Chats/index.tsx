import {ConversationTable} from './ConversationTable';
import {PersonalStatisticsCards} from './PersonalStatisticsCards';

export const Chats = () => {
  return (
    <main className="px-4 py-0 mx-auto my-0 w-full">
      <PersonalStatisticsCards />
      <ConversationTable />
    </main>
  );
};
