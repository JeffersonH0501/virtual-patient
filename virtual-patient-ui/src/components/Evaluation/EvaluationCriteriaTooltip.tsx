import { FC, useRef, useEffect, useState } from 'react';
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
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<'top' | 'bottom'>('top');

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

  const calculatePosition = () => {
    const buttonElement = document.querySelector(`[data-aspect="${aspect}"] button`);
    if (buttonElement && tooltipRef.current) {
      const buttonRect = buttonElement.getBoundingClientRect();
      const tooltipHeight = 600; // Estimated tooltip height
      const viewportHeight = window.innerHeight;
      const modalHeader = document.querySelector('[data-modal-header]');
      
      // Check if we can position above the modal header
      let preferredPosition = 'top';
      
      if (modalHeader) {
        const headerRect = modalHeader.getBoundingClientRect();
        const spaceAboveHeader = headerRect.top;
        
        // If there's enough space above the modal header, position there
        if (spaceAboveHeader > tooltipHeight + 20) {
          preferredPosition = 'top';
        } else {
          // Check space below the button
          const spaceBelow = viewportHeight - buttonRect.bottom;
          const spaceAbove = buttonRect.top;
          
          if (spaceBelow >= tooltipHeight) {
            preferredPosition = 'bottom';
          } else if (spaceAbove >= tooltipHeight) {
            preferredPosition = 'top';
          } else {
            // Not enough space in either direction, default to bottom
            preferredPosition = 'bottom';
          }
        }
      } else {
        // Fallback to normal positioning logic
        const spaceBelow = viewportHeight - buttonRect.bottom;
        const spaceAbove = buttonRect.top;
        
        if (spaceBelow >= tooltipHeight) {
          preferredPosition = 'bottom';
        } else if (spaceAbove >= tooltipHeight) {
          preferredPosition = 'top';
        } else {
          preferredPosition = 'bottom';
        }
      }
      
      setPosition(preferredPosition as 'top' | 'bottom');
    }
  };

  useEffect(() => {
    if (isVisible) {
      const timeoutId = setTimeout(calculatePosition, 0);
      
      const handleResize = () => {
        if (isVisible) {
          calculatePosition();
        }
      };
      
      window.addEventListener('resize', handleResize);
      
      return () => {
        clearTimeout(timeoutId);
        window.removeEventListener('resize', handleResize);
      };
    }
  }, [isVisible, aspect]);

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
          ref={tooltipRef}
          className={`absolute left-1/2 transform -translate-x-1/2 z-[9999] w-[600px] bg-white border border-gray-200 rounded-lg shadow-lg p-6 ${
            position === 'top' ? 'bottom-full mb-2' : 'top-full mt-2'
          }`}
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
