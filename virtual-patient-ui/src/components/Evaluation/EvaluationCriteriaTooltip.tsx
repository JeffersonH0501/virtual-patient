import { FC } from 'react';
import {Modal} from '../common/Modal';
import {X} from '../../icons';
import { useTranslation } from 'react-i18next';
import { EvaluationResult } from '../../types/evaluation';
import { useEvaluationAspects } from '../../contexts/EvaluationAspectsContext';

type EvaluationCriteriaTooltipProps = {
  aspect: EvaluationResult['aspect'];
  isVisible: boolean;
  onClose: () => void;
};


export const EvaluationCriteriaTooltip: FC<EvaluationCriteriaTooltipProps> = ({
  aspect,
  isVisible,
  onClose,
}) => {
  const { t } = useTranslation();
  const { aspects, error } = useEvaluationAspects();

  // Convert snake_case aspect to camelCase for API response
  const getAspectKey = (aspectName: EvaluationResult['aspect']) => {
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
    <Modal
      open={isVisible}
      closeAction={onClose}
      size="medium"
      containerId={`evaluation-criteria-${aspect}`}
      ariaLabel={t('evaluation.evaluationCriteria')}
    >
      <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
        <h2 className="component-title text-left">
          {t('evaluation.evaluationCriteria')}
        </h2>
        <button type="button" onClick={onClose} className="dialog-close-button" aria-label={t('common.close')}>
          <X color="currentColor" />
        </button>
      </header>
      <div className="min-h-0 overflow-y-auto p-5 text-left">
          {error || !aspects ? (
            <div className="text-center py-4">
              <p className="text-red-600 text-sm">
                {t('evaluation.aspectsLoadError')}
              </p>
            </div>
          ) : (
            <>
              <p className="text-sm text-gray-600 mb-4">
                {t('evaluation.evaluationBasedOn')}
              </p>
              <ol className="text-sm text-gray-700 space-y-2 mb-4">
                {(aspects as any)[getAspectKey(aspect)]?.map((criterion: string, criterionIndex: number) => (
                  <li key={criterionIndex} className="flex items-start gap-2">
                    <span className="text-blue-600 font-medium mt-0.5">
                      {criterionIndex + 1}.
                    </span>
                    <span>{criterion}</span>
                  </li>
                ))}
              </ol>
            </>
          )}
          {aspect !== 'completeness' && (
            <div className="border-t border-gray-200 pt-3">
              <p className="text-xs text-gray-500 mb-2">
                {t('evaluation.criteriaBuiltFrom')}
              </p>
              <ul className="text-xs text-gray-600 space-y-1">
                <li>• Communication Assessment Tool (CAT)</li>
                <li>• Escala de Habilidades de Comunicación (EHC)</li>
                <li>• Stanford Trust in Physician Scale</li>
                <li>• Medical Interview Satisfaction Scale</li>
                <li>• Patient-doctor relationship questionnaire (PDRQ-9) in primary care</li>
              </ul>
            </div>
          )}
      </div>
    </Modal>
  );
};
