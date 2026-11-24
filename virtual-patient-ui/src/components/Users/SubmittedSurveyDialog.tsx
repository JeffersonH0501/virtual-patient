import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Dialog} from '../common/Dialog';
import {evaluation, evaluationTitles, experience, sus} from '../PerceptionSurvey/questions';
import {getManagedSurvey} from '../../services/users/manageUsers';
import {Survey} from '../../services/perceptionSurvey';
import {User} from '../../types/user';

export function SubmittedSurveyDialog({account, onClose}: {account: User; onClose: () => void}) {
  const {t, i18n} = useTranslation();
  const language = i18n.resolvedLanguage?.startsWith('es') ? 'es' : 'en';
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
  return <Dialog title={t('users.surveyTitle', {name: account.name})} onClose={onClose} size="wide">
    {error ? <p role="alert">{t('perception.error')}</p> : !survey ? <p role="status">{t('common.loading')}</p> :
      <div className="submitted-survey-sections">
        {(['SUS', 'EXP', 'EVA'] as const).map((section) => <section key={section} className="dialog-reading-section dialog-reading-card dialog-reading-card--compact">
          <h3 className="default-title">{t(`perception.${section}`)}</h3>
          {section === 'SUS' && <p className="secondary-text"><strong>{t('users.surveySusScore')}:</strong> {survey.sus_score ?? '—'}</p>}
          <dl>
            {({SUS: sus, EXP: experience, EVA: evaluation})[section].map(({id, text, caption}, index) => <div key={id} className="flex items-start justify-between gap-layout border-b border-neutral-200 py-layout">
              <dt className="min-w-0 break-words secondary-text">
                <div className="text-content-muted compact-text">
                  <span className="font-semibold">{id}</span>
                  {section === 'EVA' && <span> · {evaluationTitles[index][language]}</span>}
                </div>
                <span className="block text-content">{text[language]}</span>
                {caption && <span className="block text-content-muted">{caption[language]}</span>}
              </dt>
              <dd className="shrink-0 font-semibold tabular-nums">{survey.answers[id] ?? '—'}</dd>
            </div>)}
          </dl>
          <p className="whitespace-pre-wrap break-words secondary-text"><strong>{t('users.surveyOpenAnswer')}:</strong> {survey.comments[section] || '—'}</p>
        </section>)}
      </div>}
  </Dialog>;
}
