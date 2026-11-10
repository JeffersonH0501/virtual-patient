import {ConversationTable} from './ConversationTable';
import {useTranslation} from 'react-i18next';
import {useUser} from '../../hooks';
import {Students} from '../Students';
import {PageHeader} from '../common/PageHeader';

export const Chats = () => {
  const {user} = useUser();
  const {t} = useTranslation();

  if (user?.role === 'superuser') {
    return <Students />;
  }

  return (
    <section className="ui-page">
      <PageHeader eyebrow={t('interviewsPage.eyebrow')} title={t('interviewsPage.title')} titleId="interviews-title" />
      <div className="ui-form-stack">
        <ConversationTable />
      </div>
    </section>
  );
};
