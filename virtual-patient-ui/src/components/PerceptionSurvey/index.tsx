import {Fragment, useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {evaluation, evaluationTitles, experience, sus} from './questions';
import {cachedSurvey, loadSurvey, saveSurvey, Survey} from '../../services/perceptionSurvey';
import {useUser} from '../../hooks';
import {PageHeader} from '../common/PageHeader';

const allQuestions = [...sus, ...experience, ...evaluation];
const sections = {SUS: {title: 'perceptionSusTableTitle', questions: sus}, EXP: {title: 'perceptionExpTableTitle', questions: experience}, EVA: {title: 'perceptionEvaTableTitle', questions: evaluation}} as const;
type SectionKey = keyof typeof sections;
const sectionKeys: SectionKey[] = ['SUS', 'EXP', 'EVA'];
const scaleValues = [1, 2, 3, 4, 5];

const openQuestionKeys: Record<SectionKey, string> = {
  SUS: 'perception.openQuestionSUS',
  EXP: 'perception.openQuestionEXP',
  EVA: 'perception.openQuestionEVA',
};

export function PerceptionSurvey() {
  const {t, i18n} = useTranslation();
  const {user} = useUser();
  const language = i18n.resolvedLanguage?.startsWith('es') ? 'es' : 'en';
  const prefetched = user && user.role !== 'admin' ? cachedSurvey() : null;
  const [survey, setSurvey] = useState<Survey | null>(prefetched);
  const [answers, setAnswers] = useState<Record<string, number>>(prefetched?.answers ?? {});
  const [comments, setComments] = useState<Record<string, string>>(prefetched?.comments ?? {});
  const [error, setError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    setError(false);
    if (!user || user.role === 'admin') {
      setSurvey(null); setAnswers({}); setComments({});
      return () => {
        active = false;
      };
    }
    void loadSurvey().then((data) => {
      if (active) {
        setSurvey(data); setAnswers(data.answers); setComments(data.comments);
      }
    })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [user?.id, user?.role, reload]);

  const complete = allQuestions.every(({id}) => answers[id] != null);
  const dirty = survey !== null && (
    allQuestions.some(({id}) => answers[id] !== survey.answers[id]) ||
    (['SUS', 'EXP', 'EVA'] as const).some((name) => (comments[name] ?? '') !== (survey.comments[name] ?? ''))
  );

  const persist = async (action: 'save' | 'submit') => {
    setSaving(true); setError(false); setSaved(false);
    try {
      const result = await saveSurvey(answers, comments, action); setSurvey(result); setSaved(true);
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  };

  if (user?.role === 'admin') return <div className="survey-page">{t('perceptionRoleDenied')}</div>;
  if (!survey) return <div className="survey-page" role="status">{error ? <><p role="alert">{t('perception.error')}</p><button className="ui-button ui-button--secondary" onClick={() => setReload((n) => n + 1)}>{t('perception.retry')}</button></> : t('common.loading')}</div>;
  if (!survey.eligible) return <div className="survey-page">{t('perception.locked')}</div>;

  return <div className="ui-page survey-page">
    <PageHeader eyebrow={t('perceptionEyebrow')} title={t('perception.title')} />

    {sectionKeys.map((section) => <section key={section} className="survey-section" aria-labelledby={`survey-${section}`}>
      <div className="survey-section-header">
        <h2 id={`survey-${section}`}>{t(sections[section].title)}</h2>
        <ol className="survey-scale">
          {scaleValues.map((value) => <li key={value}>
            <strong>{value}</strong>{' '}{t(`perception.scale.${value}`)}
          </li>)}
        </ol>
      </div>
      {sections[section].questions.map((question, index, list) => <Fragment key={question.id}>
        {question.group && question.group.es !== list[index - 1]?.group?.es &&
          <h3 className="survey-group-heading">{question.group[language]}</h3>
        }
        <div className="survey-question" role="radiogroup" aria-labelledby={`survey-${question.id}`}>
          <div className="survey-question-copy">
            <p className="survey-statement" id={`survey-${question.id}`}>
              {question.id}.{' '}
              {section === 'EVA' && <>{evaluationTitles[index][language]}.{' '}</>}
              {question.text[language]}
            </p>
            {question.caption && <p className="survey-caption">{question.caption[language]}</p>}
            {question.criteria &&
              <details className="survey-criteria">
                <summary>{t('perception.criteria')}</summary>
                <ul>{question.criteria.map((item) => <li key={item.es}>{item[language]}</li>)}</ul>
              </details>
            }
          </div>
          <div className="survey-choices">
            {scaleValues.map((value) => <label className="survey-choice" key={value}>
              <input
                type="radio"
                name={question.id}
                value={value}
                aria-label={`${value}. ${t(`perception.scale.${value}`)}`}
                checked={answers[question.id] === value}
                onChange={() => {
                  setAnswers((current) => ({...current, [question.id]: value}));
                  setSaved(false);
                }}
              />
              <span aria-hidden="true">{value}</span>
            </label>)}
          </div>
        </div>
      </Fragment>)}
      <label className="survey-comment">
        <span>{t(openQuestionKeys[section])} ({t('perception.optional')})</span>
        <textarea
          rows={3}
          maxLength={10000}
          value={comments[section] ?? ''}
          onChange={(event) => {
            setComments({...comments, [section]: event.target.value});
            setSaved(false);
          }}
        />
      </label>
    </section>)}

    {error && <p role="alert">{t('perception.error')}</p>}
    {saved && <p role="status" className="ui-notice ui-notice--success mx-auto w-fit max-w-full text-center">{t('perception.saved')}</p>}

    <div className="survey-actions ui-button-group ui-button-group--large">
      <button
        type="button"
        className="ui-button ui-button--primary"
        disabled={saving || !dirty || (survey.status === 'SUBMITTED' && !complete)}
        onClick={() => void persist('save')}
      >
        {t('perception.save')}
      </button>
      <button
        type="button"
        className="ui-button ui-button--primary"
        disabled={saving || !complete || (survey.status === 'SUBMITTED' && !dirty)}
        onClick={() => void persist('submit')}
      >
        {t(survey.status === 'SUBMITTED' ? 'perception.update' : 'perception.submit')}
      </button>
    </div>
  </div>;
}
