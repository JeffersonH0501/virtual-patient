import {Dialog} from '../common/Dialog';
import {FC, ReactNode} from 'react';

import {useTranslation} from 'react-i18next';
import {EvaluationCondition} from '../../types/evaluation';
import {useEvaluationAspects} from '../../contexts/EvaluationAspectsContext';
import {getAspectDisplayName} from './helpers/evaluation';

type EvaluationCriteriaTooltipProps = {
  aspect: string;
  condition?: EvaluationCondition;
  isVisible: boolean;
  onClose: () => void;
  comparison?: ReactNode;
};

export const EvaluationCriteriaTooltip: FC<EvaluationCriteriaTooltipProps> = ({
  aspect,
  isVisible,
  onClose,
  comparison,
  condition = 'TEXT_ONLY',
}) => {
  const {t} = useTranslation();
  const {aspects, multimodalAspects, error} = useEvaluationAspects();
  const metadata = multimodalAspects.find((entry) => entry.aspect === aspect);

  // Convert snake_case aspect to camelCase for API response
  const getAspectKey = (aspectName: string) => {
    switch (aspectName) {
      case 'general_communication':
        return 'generalCommunication';
      case 'show_interest':
        return 'showInterest';
      case 'show_empathy':
        return 'showEmpathy';
      case 'speak_clearly':
        return 'speakClearly';
      case 'open_communication':
        return 'openCommunication';
      case 'completeness':
        return 'completeness';
      default:
        return aspectName;
    }
  };

  return (
    <Dialog
      title={t('evaluation.evaluationCriteria')}
      open={isVisible}
      onClose={onClose}
      size={comparison ? 'large' : 'medium'}
      containerId={`evaluation-criteria-${aspect}`}
    >
      {error || !aspects ? (
        <div className="text-center py-inset">
          <p className="text-danger-600 default-text">{t('evaluation.aspectsLoadError')}</p>
        </div>
      ) : (
        <>
          <div className={aspect === 'completeness' ? 'dialog-reading-section dialog-reading-card' : undefined}>
            <p className="text-neutral-600 default-text">
              {t('evaluation.evaluationBasedOn', {component: getAspectDisplayName(aspect, t)})}
            </p>
            <ol className="dialog-list mt-layout text-neutral-700 default-text">
              {(condition === 'TEXT_PLUS_MULTIMODAL' && metadata
                ? metadata.criteria
                : (aspects as any)[getAspectKey(aspect)]
              )?.map((criterion: string, criterionIndex: number) => (
                <li key={criterionIndex}>
                  <span>{criterion}</span>
                </li>
              ))}
            </ol>
          </div>
        </>
      )}
      {comparison && (
        <section className="dialog-reading-section">
          <h3 className="default-title">{t('evaluation.clinicalCaseComparison')}</h3>
          {comparison}
        </section>
      )}
      {aspect !== 'completeness' && (
        <aside className="dialog-annotation">
          <p className="mb-[var(--layout-gap-small)] font-semibold">{t('evaluation.criteriaBuiltFrom')}</p>
          <ul className="dialog-list secondary-text">
            <li>Communication Assessment Tool (CAT)</li>
            <li>Escala de Habilidades de Comunicación (EHC)</li>
            <li>Stanford Trust in Physician Scale</li>
            <li>Medical Interview Satisfaction Scale</li>
            <li>Patient-doctor relationship questionnaire (PDRQ-9) in primary care</li>
          </ul>
        </aside>
      )}
    </Dialog>
  );
};
