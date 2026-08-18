import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { EvaluationResult } from '../../types/evaluation';
import { useEvaluationAspects } from '../../contexts/EvaluationAspectsContext';
import { QuestionMarkIcon } from '../../icons';

type EvaluationCriteriaTooltipProps = {
  aspect: EvaluationResult['aspect'];
  isVisible: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
};


export const EvaluationCriteriaTooltip: FC<EvaluationCriteriaTooltipProps> = ({
  aspect,
  isVisible,
  onMouseEnter,
  onMouseLeave
}) => {
  const { t } = useTranslation();
  const { aspects, error } = useEvaluationAspects();

  // Convert snake_case aspect to camelCase for API response
  const getAspectKey = (aspect: EvaluationResult['aspect']) => {
    switch (aspect) {
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
        return aspect;
    }
  };

  return (
    <div 
      className="relative"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      data-aspect={aspect}
    >
      <button 
      className="text-gray-400 hover:text-gray-600 transition-colors" 
      style={{ padding: "8px"}}>
        <QuestionMarkIcon size={16} />
      </button>
      {isVisible && (
        <div
          className="fixed left-1/2 top-4 z-[110] max-h-[calc(100dvh-2rem)] w-[min(600px,calc(100vw-2rem))] -translate-x-1/2 overflow-y-auto rounded-lg border border-gray-200 bg-white p-6 text-left shadow-lg [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          <h5 className="font-semibold text-gray-800 mb-3">
            {t('evaluation.evaluationCriteria')}
          </h5>
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
      )}
    </div>
  );
};
