import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Dialog} from '../common/Dialog';
import {evaluation, experience, sus} from '../PerceptionSurvey/questions';
import {getManagedSurvey} from '../../services/users/manageUsers';
import {Survey} from '../../services/perceptionSurvey';
import {User} from '../../types/user';

export function SubmittedSurveyDialog({account, onClose}: {account: User; onClose: () => void}) {
  const {t} = useTranslation();
  const [survey, setSurvey] = useState<Survey | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    void getManagedSurvey(account.id).then((value) => {
      if (active) setSurvey(value);
    }).catch(() => {
      if (active) setError(true);
    });
    return () => {
      active = false;
    };
  }, [account.id]);
  return <Dialog title={t('users.surveyTitle', {name: account.name})} onClose={onClose} size="small">
    {error ? <p role="alert">{t('perception.error')}</p> : !survey ? <p role="status">{t('common.loading')}</p> :
      <div className="grid grid-cols-1 gap-layout md:grid-cols-2">
        {(['SUS', 'EXP', 'EVA'] as const).map((section) => <section key={section}>
          <h3 className="default-title">{t(`perception.${section}`)}</h3>
          {section === 'SUS' && <p className="mb-layout text-sm"><strong>{t('users.surveySusScore')}:</strong> {survey.sus_score ?? '—'}</p>}
          <dl>
            {({SUS: sus, EXP: experience, EVA: evaluation})[section].map(({id}) => <div key={id} className="flex items-center justify-between gap-layout border-b border-neutral-100 py-1">
              <dt className="secondary-text">{id}</dt>
              <dd className="font-semibold">{survey.answers[id] ?? '—'}</dd>
            </div>)}
          </dl>
          <p className="mt-layout text-sm"><strong>{t('users.surveyOpenAnswer')}:</strong> {survey.comments[section] || '—'}</p>
        </section>)}
      </div>}
  </Dialog>;
}
