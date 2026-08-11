import { FC, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { InterviewEvaluationResponse, EvaluationResult } from '../../types/evaluation';
import { Modal } from '../common/Modal';
import { StarIcon, ComparisonIcon } from '../../icons';
import { EvaluationCriteriaTooltip } from './EvaluationCriteriaTooltip';
import { ClinicalCaseComparisonModal } from './ClinicalCaseComparisonModal';
import { useUser } from '../../hooks/useUser';
import { getAspectDisplayName, getScoreColor, getScoreLabel, sortEvaluationResults, formatDuration, calculateDuration, formatDateTime } from './helpers';

type EvaluationResultsModalProps = {
  isOpen: boolean;
  onClose: () => void;
  evaluationData: InterviewEvaluationResponse;
};

export const EvaluationResultsModal: FC<EvaluationResultsModalProps> = ({
  isOpen,
  onClose,
  evaluationData
}) => {
  const { t } = useTranslation();
  const { user } = useUser();
  const { interview, evaluationResults } = evaluationData;
  const sortedResults = sortEvaluationResults(evaluationResults);
  const averageScore = evaluationResults.reduce((sum, result) => sum + result.score, 0) / evaluationResults.length;
  const [hoveredAspect, setHoveredAspect] = useState<EvaluationResult['aspect'] | null>(null);
  const [isComparisonModalOpen, setIsComparisonModalOpen] = useState(false);

  return (
    <>
      <Modal open={isOpen} closeAction={onClose} size="fullScreen" containerId="evaluation-modal" closeOnOutsideClick={false}>
        <div className="h-full flex flex-col">
          <div className="flex items-center justify-between p-6 border-b border-gray-200 bg-white" data-modal-header>
            <h2 className="text-2xl font-bold text-gray-800">{t('evaluation.interviewEvaluationResults')}</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-4xl mx-auto space-y-6">
              {/* Interview Summary */}
              <div className="bg-gray-50 p-4 rounded-lg">
                <h3 className="text-lg font-semibold text-gray-800 mb-3">{t('evaluation.interviewSummary')}</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="font-medium text-gray-600">{t('evaluation.duration')}</span>
                    <span className="ml-2 text-gray-800">
                      {formatDuration(
                        interview.totalDuration || calculateDuration(interview.startTime, interview.endTime)
                      )}
                    </span>
                  </div>
                  <div>
                    <span className="font-medium text-gray-600">{t('evaluation.started')}</span>
                    <span className="ml-2 text-gray-800">{formatDateTime(interview.startTime)}</span>
                  </div>
                  <div>
                    <span className="font-medium text-gray-600">{t('evaluation.completed')}</span>
                    <span className="ml-2 text-gray-800">{formatDateTime(interview.endTime)}</span>
                  </div>
                </div>

              </div>

              {/* Overall Score */}
              <div className="text-center bg-gradient-to-r from-blue-50 to-indigo-50 p-6 rounded-lg">
                <h3 className="text-xl font-semibold text-gray-800 mb-2">{t('evaluation.overallPerformance')}</h3>
                <div className="flex items-center justify-center gap-2 mb-2">
                  <span className="text-3xl font-bold text-blue-600">{averageScore.toFixed(1)}</span>
                  <span className="text-gray-600">/ 10</span>
                </div>
                <div className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getScoreColor(averageScore)}`}>
                  {getScoreLabel(averageScore, t)}
                </div>
              </div>

              {/* Individual Evaluations */}
              <div className="space-y-4 pb-12">
                <h3 className="text-lg font-semibold text-gray-800">{t('evaluation.detailedFeedback')}</h3>
                {sortedResults.map((result, index) => (
                  <div key={index} className="border border-gray-200 rounded-lg p-4 relative">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-0.5">
                        <h4 className="text-md font-semibold text-gray-800">
                          {getAspectDisplayName(result.aspect, t)}
                        </h4>
                        <EvaluationCriteriaTooltip
                          aspect={result.aspect}
                          isVisible={hoveredAspect === result.aspect}
                          onMouseEnter={() => setHoveredAspect(result.aspect)}
                          onMouseLeave={() => setHoveredAspect(null)}
                        />
                        {result.aspect === 'completeness' && (user?.role === 'teacher' || user?.role === 'superuser') && (
                          <button
                            style={{ padding: "8px"}}
                            onClick={() => setIsComparisonModalOpen(true)}
                            className="text-blue-600 hover:text-blue-800 transition-colors"
                            title={t('evaluation.clinicalCaseComparison')}
                          >
                            <ComparisonIcon size={20} />
                          </button>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="flex items-center gap-1">
                          {[...Array(5)].map((_, i) => (
                            <div
                              key={i}
                              className={`w-4 h-4 ${
                                i < Math.floor(result.score / 2) 
                                  ? 'text-yellow-400' 
                                  : 'text-gray-300'
                              }`}
                            >
                              <StarIcon />
                            </div>
                          ))}
                        </div>
                        <span className={`px-2 py-1 rounded-full text-sm font-medium ${getScoreColor(result.score)}`}>
                          {result.score}/10
                        </span>
                      </div>
                    </div>
                    <p className="text-gray-700 leading-relaxed">{result.feedback}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </Modal>
      
      {/* Clinical Case Comparison Modal - Outside main modal to avoid nesting */}
      {interview.clinicalCase && interview.progressSummary && (
        <ClinicalCaseComparisonModal
          isOpen={isComparisonModalOpen}
          onClose={() => setIsComparisonModalOpen(false)}
          clinicalCase={interview.clinicalCase}
          progressSummary={interview.progressSummary}
          hypotheses={interview.hypotheses}
        />
      )}
    </>
  );
};
