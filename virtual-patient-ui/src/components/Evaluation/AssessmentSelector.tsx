import {ComponentProps, useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Plus} from 'lucide-react';
import {gradingRequest, HumanRating, Reviewer, Workspace} from '../../services/teacherGrading';
import {useUser} from '../../hooks/useUser';
import {EvaluationResult} from '../../types/evaluation';
import {EvaluationResultsPanel} from './EvaluationResultsPanel';
import {AssignmentDialog} from '../Students/AssignmentDialog';
import {Button} from '../common';
import {MotionPresence} from '../common/Motion';
import {HumanRatingPanel} from './HumanRatingPanel';

export const AssessmentSelector = ({
  canAssignTeachers = false,
  ...props
}: Omit<ComponentProps<typeof EvaluationResultsPanel>,
  'assessmentControls' | 'headerAction' | 'selectedCondition' | 'onEditScore' | 'editorContent'
> & {canAssignTeachers?: boolean}) => {
  const {t} = useTranslation();
  const {user} = useUser();
  const isAdmin = user?.role === 'superuser';
  const isSelf = !isAdmin && props.evaluationData.interview.isOwner === true;
  const canManageTeachers = canAssignTeachers && isAdmin;
  const interviewId = props.evaluationData.interview.id;
  const defaultSource = isAdmin ? 'TEXT_ONLY' : 'TEXT_PLUS_MULTIMODAL';
  const [source, setSource] = useState(defaultSource);
  const [ratings, setRatings] = useState<HumanRating[]>([]);
  const [reviewers, setReviewers] = useState<Reviewer[]>([]);
  const [selfRating, setSelfRating] = useState<Workspace | null>(null);
  const [assigning, setAssigning] = useState(false);
  const [editingAspect, setEditingAspect] = useState<string | null>(null);
  const [editingBusy, setEditingBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(0);
  const load = async () => {
    const token = ++request.current;
    try {
      if (isSelf) {
        const saved = await gradingRequest<Workspace>('/medical-interviews/' + interviewId + '/self-rating');
        if (request.current !== token) return;
        setSelfRating(saved);
      } else {
        const [saved, people] = await Promise.all([
          gradingRequest<HumanRating[]>('/medical-interviews/' + interviewId + '/teacher-ratings'),
          gradingRequest<Reviewer[]>('/medical-interviews/' + interviewId + '/reviewers'),
        ]);
        if (request.current !== token) return;
        const visible = isAdmin ? people : people.filter((person) => person.teacherId === user?.id);
        setRatings(saved);
        setReviewers(visible);
        setSource((current) => current.startsWith('teacher:') &&
          !visible.some((person) => current === 'teacher:' + person.assignmentId) ? defaultSource : current);
      }
      setError('');
    } catch {
      if (request.current === token) setError(t('errors.generic'));
    }
  };
  useEffect(() => {
    setRatings([]);
    setReviewers([]);
    setSelfRating(null);
    setSource(defaultSource);
    setAssigning(false);
    setEditingAspect(null);
    setError('');
    void load();
    return () => {
      request.current += 1;
    };
  }, [interviewId, defaultSource, isSelf, user?.id]);
  const isHuman = source === 'self' || source.startsWith('teacher:');
  const reviewer = reviewers.find((person) => 'teacher:' + person.assignmentId === source);
  const ownAssignment = user?.role === 'teacher' && reviewer?.teacherId === user.id &&
    reviewer.status === 'submitted' ? reviewer : undefined;
  const canEditSelf = source === 'self' && selfRating?.status === 'submitted';
  const selected = source === 'self' && selfRating?.status === 'submitted'
    ? {results: selfRating.results as EvaluationResult[], overallScore: selfRating.overallScore}
    : ratings.find((rating) => rating.id === reviewer?.ratingId);
  const humanLabel = source === 'self' ? t('grading.selfAssessment') :
    isAdmin ? t('grading.teacherEvaluation', {name: reviewer?.teacherName}) : t('grading.yourEvaluation');
  const data = isHuman ? {
    ...props.evaluationData,
    evaluationResults: selected?.results ?? [],
    multimodalEvaluationResults: [],
    interview: {...props.evaluationData.interview, multimodalInterviewEvaluation: undefined,
      interviewEvaluation: selected && selected.overallScore !== null ? {
        ...props.evaluationData.interview.interviewEvaluation!,
        overallScore: selected.overallScore,
      } : undefined},
  } : props.evaluationData;
  const options = [
    ...(isAdmin ? [{value: 'TEXT_ONLY', label: t('grading.automaticTextBased')}] : []),
    {value: 'TEXT_PLUS_MULTIMODAL', label: t(isAdmin ? 'grading.automaticMultimodalEvidence' : 'grading.automaticEvaluation')},
    ...(isSelf ? [{value: 'self', label: t('grading.selfAssessment')}] :
      reviewers.map((person) => ({value: 'teacher:' + person.assignmentId,
        label: isAdmin ? t('grading.teacherEvaluation', {name: person.teacherName}) : t('grading.yourEvaluation')}))),
  ];
  const controls = <div className="assessment-controls">
    <div role="group" aria-label={t('grading.evaluationSource')}
      className="flex w-full flex-wrap items-center justify-center gap-layout">
      {options.map(({value, label}) => <button key={value} type="button"
        className={'ui-navigation-link min-w-0 break-words text-center ' + (source === value ? 'ui-navigation-link--active' : '')}
        aria-pressed={source === value} disabled={editingBusy} onClick={() => {
          if (source === value) return;
          setEditingAspect(null);
          setSource(value);
        }}>{label}</button>)}
    </div>
    {error && <div className="flex items-center justify-center gap-layout">
      <span role="alert" className="text-danger-700 secondary-text">{error}</span>
      <Button variant="text" onClick={() => void load()}>{t('common.retry')}</Button>
    </div>}
  </div>;
  return <>
    <EvaluationResultsPanel key={interviewId} {...props} evaluationData={data}
      hideConditionSelector assessmentControls={controls} isLoading={!isHuman && props.isLoading}
      headerAction={canManageTeachers && <span className="panel-header-action">
        <button type="button" className="ui-icon-button" aria-label={t('grading.assignTeacher')}
          title={t('grading.assignTeacher')} aria-haspopup="dialog" disabled={editingBusy}
          onClick={() => setAssigning(true)}><Plus aria-hidden="true" /></button>
      </span>}
      onEditScore={ownAssignment || canEditSelf ? (aspect) => setEditingAspect(aspect) : undefined}
      editorContent={(ownAssignment || canEditSelf) && editingAspect ? <HumanRatingPanel
        assignmentId={ownAssignment?.assignmentId} selfInterviewId={canEditSelf ? interviewId : undefined}
        aspectToEdit={editingAspect} onBusyChange={setEditingBusy} onCancel={() => setEditingAspect(null)}
        onSubmitted={async () => {
          await load();
          setEditingAspect(null);
        }} /> : undefined}
      assessmentKey={source} selectedCondition={source === 'TEXT_PLUS_MULTIMODAL' ? 'TEXT_PLUS_MULTIMODAL' : 'TEXT_ONLY'}
      humanLabel={isHuman ? humanLabel : undefined} pendingMessage={isHuman ? t('grading.ratingPending') : undefined}
      canRegenerate={props.canRegenerate && (!isHuman || Boolean(props.onReprocess))}
      onRegenerate={isHuman ? undefined : props.onRegenerate} isRegenerating={!isHuman && props.isRegenerating} />
    <MotionPresence visible={assigning && canManageTeachers}>
      {assigning && canManageTeachers && <AssignmentDialog interviewId={interviewId}
        onClose={() => setAssigning(false)} onSaved={() => void load()} />}
    </MotionPresence>
  </>;
};

