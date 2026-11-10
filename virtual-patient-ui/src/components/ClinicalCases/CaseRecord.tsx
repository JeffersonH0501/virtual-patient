import {useTranslation} from 'react-i18next';
import {caseLabels, caseSections} from './caseSections';

const compactFields = new Set(['genderRestriction', 'femaleName', 'maleName', 'age', 'weightInKg', 'socioeconomicStatus']);

/** Original case fields, without generated summaries or assessment results. */
export const CaseRecord = ({data, reading = false}: {data: object; reading?: boolean}) => {
  const {t} = useTranslation();
  const fields = data as Record<string, unknown>;
  return (
    <div className={reading ? 'case-record-reading' : 'case-record'}>
      {caseSections.map((section) => (
        <section className={reading ? 'dialog-reading-section dialog-reading-card' : 'case-record-section'} key={section.title}>
          <h3 className={reading ? undefined : 'mb-layout default-title'}>{t(section.title)}</h3>
          <dl className="case-record-fields">
            {section.fields.map((field) => (
              <div className={compactFields.has(field) ? 'min-w-0' : 'min-w-0 case-record-field-wide'} key={field}>
                <dt className="text-content-muted secondary-text">
                  {t('clinicalCaseFields.' + caseLabels[field])}
                </dt>
                <dd className="whitespace-pre-wrap break-words default-text">
                  {String(fields[field] ?? '—') || '—'}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
};
