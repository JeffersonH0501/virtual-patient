import {ReactNode} from 'react';
import {useTranslation} from 'react-i18next';
import {Badge} from '../common/Badge';
import {CaseRecord} from '../ClinicalCases/CaseRecord';
import {TranslatedClinicalCase} from '../../types/clinicalCase';
import {ProgressSummary} from '../../types/progress';

type Props = {
  clinicalCase?: TranslatedClinicalCase | null;
  progressSummary?: ProgressSummary | null;
  hypotheses?: {id: number; interviewId: number; hypothesisText: string; hypothesisOrder: number}[];
};

/** Compare case facts with the collected information without modifying either source. */
export const ClinicalCaseComparison = ({
  clinicalCase,
  progressSummary,
  hypotheses,
}: Props) => {
  const {t} = useTranslation();
  const unavailable = t('conversations.notAvailable');
  const renderItems = (items?: object[] | null) =>
    items?.length ? (
      <div className="ui-form-stack">
        {items.map((item, index) => (
          <dl key={index} className="dialog-detail-list">
            {Object.entries(item)
              .filter(([, value]) => value != null && value !== '')
              .map(([key, value]) => (
                <div key={key}>
                  <dt className="secondary-text text-content-muted">
                    {t('dialog.detailLabels.' + key)}
                  </dt>
                  <dd>
                    {key === 'status' ? (
                      <Badge tone={value === 'Active' ? 'danger' : 'neutral'}>{String(value)}</Badge>
                    ) : (
                      String(value)
                    )}
                  </dd>
                </div>
              ))}
          </dl>
        ))}
      </div>
    ) : null;
  const symptoms = [
    ...(progressSummary?.currentSymptoms ?? []),
    ...(progressSummary?.currentIllnesses ?? []),
  ];
  const rows: {label: string; original?: keyof TranslatedClinicalCase; summary?: ReactNode}[] = clinicalCase && progressSummary ? [
    {label: 'clinicalCases.title', original: 'titleTranslations'},
    {
      label: 'clinicalCases.description',
      original: 'descriptionTranslations',
      summary: progressSummary.summaryText,
    },
    {label: 'clinicalCaseFields.chiefComplaint', original: 'chiefComplaintTranslations'},
    {
      label: 'clinicalCaseFields.presentIllness',
      original: 'presentIllnessTranslations',
      summary: renderItems(symptoms),
    },
    {
      label: 'clinicalCaseFields.personalMedicalHistory',
      original: 'personalMedicalHistoryTranslations',
      summary: renderItems(progressSummary.medicalHistory),
    },
    {label: 'clinicalCaseFields.surgicalHistory', original: 'surgicalHistoryTranslations'},
    {
      label: 'clinicalCaseFields.medications',
      original: 'medicationsTranslations',
      summary: renderItems(progressSummary.medications),
    },
    {
      label: 'clinicalCaseFields.habits',
      original: 'habitsTranslations',
      summary: renderItems(progressSummary.habits),
    },
    {
      label: 'clinicalCaseFields.allergies',
      original: 'allergiesTranslations',
      summary: progressSummary.allergies,
    },
    {
      label: 'clinicalCaseFields.familyHistory',
      original: 'familyHistoryTranslations',
      summary: renderItems(progressSummary.familyHistory),
    },
    {label: 'clinicalCaseFields.concerns', original: 'concernsTranslations'},
    {
      label: 'clinicalCaseFields.specialPhysicalRequirements',
      original: 'physicalRequirementsTranslations',
    },
    {label: 'clinicalCaseFields.socioeconomicCondition', original: 'socioeconomicStatusTranslations'},
    {label: 'clinicalCaseFields.patientContext', original: 'patientContextTranslations'},
    {label: 'patientProfile.dietInformation', summary: progressSummary.dietInformation},
    {label: 'patientProfile.workInformation', summary: progressSummary.workInformation},
  ] : [];
  return (
    <>
      {clinicalCase && !progressSummary && <CaseRecord data={clinicalCase} reading />}
      {rows.map((row) => (
        <section className="dialog-comparison-field dialog-reading-card" key={row.label}>
          <h4 className="medium-text">{t(row.label)}</h4>
          <div className="dialog-comparison-values">
            <div>
              <h5 className="secondary-text text-content-muted">
                {t('evaluation.originalClinicalCase')}
              </h5>
              <p className="whitespace-pre-wrap">
                {row.original ? clinicalCase?.[row.original]?.es || unavailable : unavailable}
              </p>
            </div>
            <div>
              <h5 className="secondary-text text-content-muted">
                {t('evaluation.studentSummary')}
              </h5>
              {row.summary ? (
                <div className="dialog-comparison-summary">{row.summary}</div>
              ) : (
                <p>{unavailable}</p>
              )}
            </div>
          </div>
        </section>
      ))}
      {Boolean(hypotheses?.length) && (
        <section className="dialog-comparison-field dialog-reading-card">
          <h4 className="medium-text">{t('clinicalChat.submittedHypotheses')}</h4>
          <ol className="numbered-list space-y-1">
            {[...(hypotheses ?? [])]
              .sort((a, b) => a.hypothesisOrder - b.hypothesisOrder)
              .map((item) => <li key={item.id}>{item.hypothesisText}</li>)}
          </ol>
        </section>
      )}
    </>
  );
};
