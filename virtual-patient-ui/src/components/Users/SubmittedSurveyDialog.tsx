import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Dialog} from '../common/Dialog';
import {cuq, evaluation, evaluationTitles} from '../PerceptionSurvey/questions';
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
  return <Dialog title={t('users.surveyTitle', {name: account.name})} onClose={onClose} size="large">
    {error ? <p role="alert">{t('perception.error')}</p> : !survey ? <p role="status">{t('common.loading')}</p> :
      <div className="space-y-layout">
        {survey.cuq_score != null && <p>{t('users.surveyScore')}: {survey.cuq_score.toFixed(1)} / 100</p>}
        {(['CUQ', 'EVA'] as const).map((section) => <section key={section}>
          <h3 className="default-title">{t(section === 'CUQ' ? 'perceptionCuqTableTitle' : 'perceptionEvaTableTitle')}</h3>
          <ol className="space-y-layout">
            {(section === 'CUQ' ? cuq : evaluation).map((question, index) => <li key={question.id}>
              <p><strong>{question.id}.</strong> {section === 'EVA' && <>{evaluationTitles[index][language]}. </>}{question.text[language]}</p>
              {question.caption && <p className="secondary-text">{question.caption[language]}</p>}
              {question.criteria && <details><summary>{t('perception.criteria')}</summary><ul>{question.criteria.map((criterion) => <li key={criterion.es}>{criterion[language]}</li>)}</ul></details>}
              <p>{survey.answers[question.id] != null ? `${survey.answers[question.id]} · ${t(`perception.scale.${survey.answers[question.id]}`)}` : t('conversations.notAvailable')}</p>
            </li>)}
          </ol>
          <p><strong>{t('perception.openQuestion')}:</strong> {survey.comments[section] || '—'}</p>
        </section>)}
      </div>}
  </Dialog>;
}
