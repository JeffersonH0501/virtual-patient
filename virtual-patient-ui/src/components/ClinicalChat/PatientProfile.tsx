import {Badge} from '../common/Badge';
import {MotionDetails} from '../common/Motion';
import {useAppMotion} from '../common/Motion/hooks';
import {FC, ReactNode, useLayoutEffect, useRef} from 'react';
import {useTranslation} from 'react-i18next';
import {Patient} from '../../types';
import {TagGroup} from './TagGroup';
import {Personality} from '../../types/personality';
import {readDesignNumber} from '../../utils/designTokens';

const PatientDetailCard = ({title, status, fields}: {
  title: string;
  status?: string | null;
  fields: [string, string | null | undefined][];
}) => {
  const {t} = useTranslation();
  return (
    <article className="dialog-reading-card dialog-reading-card--compact">
      <header className="flex flex-wrap items-center justify-between gap-x-layout gap-y-1">
        <h4 data-preserve-case className="min-w-0 break-words text-content default-title">
          {title}
        </h4>
        {status && (
          <Badge tone="info" className="py-1 leading-tight">
            {status}
          </Badge>
        )}
      </header>
      <dl className="mt-layout grid gap-y-[var(--layout-gap-small)] empty:hidden">
        {fields.filter(([, value]) => value).map(([label, value]) => (
          <div key={label} className="grid grid-cols-patient-details items-start gap-layout">
            <dt className="break-words text-content-muted compact-text leading-tight">{t(`patientProfile.${label}`)}</dt>
            <dd className="min-w-0 whitespace-pre-wrap break-words text-content secondary-text leading-tight">{value}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
};

type PatientProfileProps = {
  patient: Patient;
  caseTitle?: string;
  personality?: Personality | null;
  headerAction?: ReactNode;
  children?: ReactNode;
  basicOnly?: boolean;
  isReview?: boolean;
};

export const PatientProfile: FC<PatientProfileProps> = ({
  patient,
  caseTitle,
  personality,
  headerAction,
  children,
  isReview = false,
  basicOnly = false,
}) => {
  const {t} = useTranslation();
  const {enabled, reduced} = useAppMotion();
  const panelRef = useRef<HTMLDivElement>(null);
  const sectionPositions = useRef(new Map<HTMLElement, number>());
  const previousSectionOrder = useRef<string[]>([]);


  const {gender, age, weight} = patient.basicInfo;
  const genderLabel = gender === 'male' || gender === 'female'
    ? t(`clinicalSession.${gender}`)
    : gender;
  const rows: [string, ReactNode][] = isReview ? [
    ['patientProfile.case', caseTitle],
    ['patientProfile.personality', personality?.name],
    ['patientProfile.gender', genderLabel],
  ] : [
    ['patientProfile.case', caseTitle],
    ['patientProfile.name', patient.name],
    ['patientProfile.gender', genderLabel],
    ['patientProfile.age', age ? t('clinicalCases.ageValue', {age}) : null],
    ['patientProfile.weight', weight],
    ['patientProfile.personality', personality?.name],
  ];

  const sections: [string, ReactNode][] = [
    ['currentSymptoms', (patient.symptoms && patient.symptoms.length > 0) ? (
      <TagGroup tags={patient.symptoms} tone="warning" />
    ) : null],
    ['allergies', (patient.allergies && patient.allergies.length > 0) ? (
      <TagGroup tags={patient.allergies} />
    ) : null],
    ['diet', (patient.diet && patient.diet.trim() !== '') ? (
      <p className="whitespace-pre-wrap break-words text-content default-text">
        {patient.diet}
      </p>
    ) : null],
    ['currentIllnesses', patient.illnesses?.length ? (
      <div className="space-y-layout">
        {patient.illnesses.map((illness, index) => (
          <PatientDetailCard key={index} title={illness.illness} status={illness.status} fields={[
            ['diagnosed', illness.diagnosisDate],
            ['severity', illness.severity],
            ['treatment', illness.treatment],
            ['notes', illness.notes],
          ]} />
        ))}
      </div>
    ) : null],
    ['medications', patient.medications?.length ? (
      <div className="space-y-layout">
        {patient.medications.map((medication, index) => (
          <PatientDetailCard key={index} title={medication.medication} fields={[
            ['dosage', medication.dosage],
            ['frequency', medication.frequency],
            ['duration', medication.duration],
            ['purpose', medication.purpose],
          ]} />
        ))}
      </div>
    ) : null],
    ['familyHistory', patient.familyHistory?.length ? (
      <div className="space-y-layout">
        {patient.familyHistory.map((familyMember, index) => (
          <PatientDetailCard key={index} title={familyMember.relationship} fields={[
            ['condition', familyMember.condition],
            ['notes', familyMember.notes],
          ]} />
        ))}
      </div>
    ) : null],
    ['habits', patient.habits?.length ? (
      <div className="space-y-layout">
        {patient.habits.map((habit, index) => (
          <PatientDetailCard key={index} title={habit.habit} fields={[
            ['duration', habit.duration],
            ['frequency', habit.frequency],
          ]} />
        ))}
      </div>
    ) : null],
    ['workInformation', (patient.workInformation && patient.workInformation.trim() !== '') ? (
      <p className="whitespace-pre-wrap break-words text-content default-text">
        {patient.workInformation}
      </p>
    ) : null],
    ['medicalHistory', patient.medicalHistory?.length ? (
      <div className="space-y-layout">
        {patient.medicalHistory.map((history, index) => (
          <PatientDetailCard key={index} title={history.type} fields={[
            ['date', history.date],
            ['description', history.description],
            ['outcome', history.outcome],
          ]} />
        ))}
      </div>
    ) : null],
    ['summary', (patient.summary) ? (
      <p className="whitespace-pre-wrap break-words text-content default-text">
        {patient.summary}
      </p>
    ) : null],
  ];
  sections.sort(([leftTitle, left], [rightTitle, right]) => {
    if (!left || !right) return Number(Boolean(right)) - Number(Boolean(left));
    return previousSectionOrder.current.indexOf(leftTitle) - previousSectionOrder.current.indexOf(rightTitle);
  });
  const sectionOrder = sections.map(([title]) => title).join(',');

  useLayoutEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    previousSectionOrder.current = sectionOrder.split(',');
    const details = Array.from(panel.querySelectorAll<HTMLElement>(':scope > .patient-profile-details'));
    const measure = () => new Map(details.map((row) => [row, row.offsetTop]));
    const nextPositions = measure();
    const animations: Animation[] = [];
    if (enabled && !reduced) {
      const duration = readDesignNumber('--app-motion-expand');
      for (const [row, position] of nextPositions) {
        const previous = sectionPositions.current.get(row);
        if (previous !== undefined && previous !== position && row.animate) {
          animations.push(row.animate(
            [{transform: `translateY(${previous - position}px)`}, {transform: 'none'}],
            {duration, easing: 'ease-in-out'},
          ));
        }
      }
    }
    sectionPositions.current = nextPositions;
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => {
      sectionPositions.current = measure();
    });
    observer?.observe(panel);
    details.forEach((row) => observer?.observe(row));
    return () => {
      observer?.disconnect();
      animations.forEach((animation) => animation.cancel());
    };
  }, [enabled, reduced, sectionOrder]);

  return (
    <div ref={panelRef} className={`ui-panel min-h-0 w-full min-w-0 ${isReview ? 'flex flex-col overflow-hidden' : `overflow-x-hidden overflow-y-auto scrollbar-hidden ${basicOnly ? 'shrink-0 md:max-h-[45%]' : 'flex-1'}`}`}>
      <div className={`ui-panel-header sticky top-0 z-10 shrink-0 bg-surface ${headerAction ? 'ui-panel-header--title-sized' : ''}`}>
        <h2 className="text-left default-title">{t('patientProfile.interviewSummary')}</h2>
        {headerAction}
      </div>
      <section className={`ui-panel-section patient-profile-summary ${isReview ? 'shrink-0' : ''}`}>
        <dl className={`interview-summary-details default-text ${isReview ? 'interview-summary-details--review' : ''}`}>
          {rows.map(([label, value]) => (
            <div key={label} className="interview-summary-pair">
              <dt className="text-left text-neutral-500 default-text">{t(label)}:</dt>
              {isReview && ' '}
              <dd className="min-w-0 break-words text-neutral-800 default-text text-right">
                {value || '—'}
              </dd>
            </div>
          ))}
        </dl>
      </section>
      {!basicOnly && !isReview && sections.map(([title, content]) => (
        <MotionDetails key={title}
          className={content ? 'patient-profile-details patient-profile-details--filled' : 'patient-profile-details'}
          summary={t(`patientProfile.${title}`)}>
          <div className="pb-layout text-left">
            {content ?? <p className="text-content-muted secondary-text">{t('patientProfile.emptySection')}</p>}
          </div>
        </MotionDetails>
      ))}
      {children}
    </div>
  );
};
