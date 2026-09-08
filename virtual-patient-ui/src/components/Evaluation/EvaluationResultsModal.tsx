import { FC, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { InterviewEvaluationResponse, EvaluationResult } from '../../types/evaluation';
import { Modal } from '../common/Modal';
import { ComparisonIcon, X } from '../../icons';
import {EvaluationScore} from '../common';
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
  evaluationData,
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
      <Modal open={isOpen} closeAction={onClose} size="large" containerId="evaluation-modal">
        <div className="h-full flex flex-col">
          <div className="flex items-center justify-between p-6 border-b border-gray-200 bg-white" data-modal-header>
            <h2 className="text-2xl font-bold text-gray-800">{t('evaluation.interviewEvaluationResults')}</h2>
            <button
              onClick={onClose}
              className="dialog-close-button"
              aria-label={t('common.close')}
              title={t('common.close')}
            >
              <span className="block h-6 w-6 [&_svg]:h-full [&_svg]:w-full"><X color="currentColor" /></span>
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-4xl mx-auto space-y-6">
              {/* Interview Summary */}
              <div className="bg-gray-50 p-4 rounded-lg">
                <h3 className="mb-3 text-lg font-semibold text-slate-900">{t('evaluation.interviewSummary')}</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="font-medium text-gray-600">{t('evaluation.duration')}</span>
                    <span className="ml-2 text-gray-800">
                      {formatDuration(
                        interview.totalDuration || calculateDuration(interview.startTime, interview.endTime),
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
                <EvaluationScore score={averageScore} size="large" className="mb-2" />
                <div className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getScoreColor(averageScore)}`}>
                  {getScoreLabel(averageScore, t)}
                </div>
              </div>

              {/* Individual Evaluations */}
              <div className="space-y-4 pb-12">
                <h3 className="text-lg font-semibold text-gray-800">{t('evaluation.detailedFeedback')}</h3>
                {sortedResults.map((result, index) => (
                  <div
                    key={index}
                    className="relative rounded-panel border border-slate-200 bg-white p-4 shadow-card"
                  >
                    <div className="mb-3 flex items-start justify-between gap-3">
                      <div className="flex items-center gap-0.5">
                        <h4
                          role="button"
                          tabIndex={0}
                          aria-expanded={hoveredAspect === result.aspect}
                          onClick={() => setHoveredAspect(
                            hoveredAspect === result.aspect ? null : result.aspect,
                          )}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              setHoveredAspect(hoveredAspect === result.aspect ? null : result.aspect);
                            }
                          }}
                          className="text-md cursor-pointer font-semibold text-slate-900 underline decoration-current underline-offset-2 transition-colors hover:text-blue-700 focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-300"
                        >
                          {getAspectDisplayName(result.aspect, t)}
                        </h4>
                        <EvaluationCriteriaTooltip
                          aspect={result.aspect}
                          isVisible={hoveredAspect === result.aspect}
                          onClose={() => setHoveredAspect(null)}
                        />
                        {result.aspect === 'completeness' && (user?.role === 'teacher' || user?.role === 'superuser') && (
                          <button
                            data-evaluation-row="true"
                            onClick={() => setIsComparisonModalOpen(true)}
                            className="text-blue-600 hover:text-blue-800 transition-colors [&_svg]:h-6 [&_svg]:w-6"
                            title={t('evaluation.clinicalCaseComparison')}
                          >
                            <ComparisonIcon />
                          </button>
                        )}
                      </div>
                      <div className="flex items-center">
                        <EvaluationScore score={result.score} size="small" />
                      </div>
                    </div>
                    <p className="leading-relaxed text-slate-600">{result.feedback}</p>
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
