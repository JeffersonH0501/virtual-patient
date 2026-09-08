import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../common/Modal';
import { TranslatedClinicalCase } from '../../types/clinicalCase';
import { ProgressSummary } from '../../types/progress';
import {ClipboardText, FileText, X} from '../../icons';

type ClinicalCaseComparisonModalProps = {
  isOpen: boolean;
  onClose: () => void;
  clinicalCase: TranslatedClinicalCase;
  progressSummary: ProgressSummary;
  hypotheses?: {
    id: number;
    interviewId: number;
    hypothesisText: string;
    hypothesisOrder: number;
  }[];
};

export const ClinicalCaseComparisonModal: FC<ClinicalCaseComparisonModalProps> = ({
  isOpen,
  onClose,
  clinicalCase,
  progressSummary,
  hypotheses,
}) => {
  const { t } = useTranslation();

  const handleClose = (event?: any) => {
    if (event) {
      event.stopPropagation();
      event.preventDefault();
      event.stopImmediatePropagation();
    }

    onClose();
  };

  return (
    <Modal open={isOpen} closeAction={handleClose} size="large" containerId='clinical-case-comparison-modal'>
      <div className="h-full flex flex-col">
        <div className="flex items-center justify-between p-6 border-b border-gray-200 bg-white">
          <h2 className="text-2xl font-bold text-gray-800">
            {t('evaluation.clinicalCaseComparison')}
          </h2>
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
          <div className="max-w-7xl mx-auto">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Original Clinical Case */}
              <div className="bg-blue-50 rounded-lg p-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center">
                    <span className="block h-4 w-4 [&_svg]:h-full [&_svg]:w-full"><FileText color="currentColor" /></span>
                  </div>
                  <h3 className="text-xl font-semibold text-blue-800">
                    {t('evaluation.originalClinicalCase')}
                  </h3>
                </div>

                <div className="space-y-4">
                  {/* Case Title */}
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-2">{t('clinicalCases.title')}</h4>
                    <p className="text-gray-700">{clinicalCase.titleTranslations.es}</p>
                  </div>

                  {/* Case Description */}
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-2">{t('clinicalCases.description')}</h4>
                    <p className="text-gray-700">{clinicalCase.descriptionTranslations.es}</p>
                  </div>

                  {/* Chief Complaint */}
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.chiefComplaint')}</h4>
                    <p className="text-gray-700">{clinicalCase.chiefComplaintTranslations.es}</p>
                  </div>

                  {/* Present Illness */}
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.presentIllness')}</h4>
                    <p className="text-gray-700">{clinicalCase.presentIllnessTranslations.es}</p>
                  </div>

                  {/* Medical History */}
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.personalMedicalHistory')}</h4>
                    <p className="text-gray-700">{clinicalCase.personalMedicalHistoryTranslations.es}</p>
                  </div>

                  {/* Medications */}
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.medications')}</h4>
                    <p className="text-gray-700">{clinicalCase.medicationsTranslations.es}</p>
                  </div>

                  {/* Habits */}
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.habits')}</h4>
                    <p className="text-gray-700">{clinicalCase.habitsTranslations.es}</p>
                  </div>

                  {/* Allergies */}
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.allergies')}</h4>
                    <p className="text-gray-700">{clinicalCase.allergiesTranslations.es}</p>
                  </div>

                  {/* Family History */}
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.familyHistory')}</h4>
                    <p className="text-gray-700">{clinicalCase.familyHistoryTranslations.es}</p>
                  </div>

                  {/* Concerns */}
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.concerns')}</h4>
                    <p className="text-gray-700">{clinicalCase.concernsTranslations.es}</p>
                  </div>
                </div>
              </div>

              {/* Student's Summary */}
              <div className="bg-green-50 rounded-lg p-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-8 h-8 bg-green-600 rounded-full flex items-center justify-center">
                    <span className="block h-4 w-4 [&_svg]:h-full [&_svg]:w-full"><ClipboardText color="currentColor" /></span>
                  </div>
                  <h3 className="text-xl font-semibold text-green-800">
                    {t('evaluation.studentSummary')}
                  </h3>
                </div>

                <div className="space-y-4">
                  {/* Summary Text */}
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-2">{t('evaluation.summaryText')}</h4>
                    <p className="text-gray-700">{progressSummary.summaryText}</p>
                  </div>

                  {/* Current Symptoms */}
                  {progressSummary.currentSymptoms && progressSummary.currentSymptoms.length > 0 && (
                    <div>
                      <h4 className="font-semibold text-gray-800 mb-2">{t('evaluation.currentSymptoms')}</h4>
                      <div className="space-y-2">
                        {progressSummary.currentSymptoms.map((symptom, index: number) => (
                          <div key={index} className="bg-white rounded p-3 border border-green-200">
                            <div className="flex justify-between items-start">
                              <span className="font-medium text-gray-800">{symptom.symptom}</span>
                              <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                symptom.status === 'Active' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'
                              }`}>
                                {symptom.status}
                              </span>
                            </div>
                            {symptom.severity && (
                              <p className="text-sm text-gray-600 mt-1">
                                <span className="font-medium">Severity:</span> {symptom.severity}
                              </p>
                            )}
                            {symptom.location && (
                              <p className="text-sm text-gray-600">
                                <span className="font-medium">Location:</span> {symptom.location}
                              </p>
                            )}
                            {symptom.triggers && (
                              <p className="text-sm text-gray-600">
                                <span className="font-medium">Triggers:</span> {symptom.triggers}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Current Illnesses */}
                  {progressSummary.currentIllnesses && progressSummary.currentIllnesses.length > 0 && (
                    <div>
                      <h4 className="font-semibold text-gray-800 mb-2">{t('evaluation.currentIllnesses')}</h4>
                      <div className="space-y-2">
                        {progressSummary.currentIllnesses.map((illness, index: number) => (
                          <div key={index} className="bg-white rounded p-3 border border-green-200">
                            <div className="flex justify-between items-start">
                              <span className="font-medium text-gray-800">{illness.illness}</span>
                              <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                illness.status === 'Active' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'
                              }`}>
                                {illness.status}
                              </span>
                            </div>
                            {illness.severity && (
                              <p className="text-sm text-gray-600 mt-1">
                                <span className="font-medium">Severity:</span> {illness.severity}
                              </p>
                            )}
                            {illness.treatment && (
                              <p className="text-sm text-gray-600">
                                <span className="font-medium">Treatment:</span> {illness.treatment}
                              </p>
                            )}
                            {illness.notes && (
                              <p className="text-sm text-gray-600">
                                <span className="font-medium">Notes:</span> {illness.notes}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Additional Information */}
                  {progressSummary.allergies && (
                    <div>
                      <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.allergies')}</h4>
                      <p className="text-gray-700">{progressSummary.allergies}</p>
                    </div>
                  )}

                  {progressSummary.medications && progressSummary.medications.length > 0 && (
                    <div>
                      <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.medications')}</h4>
                      <div className="space-y-2">
                        {progressSummary.medications.map((medication, index: number) => (
                          <div key={index} className="bg-white rounded p-3 border border-green-200">
                            <div className="font-medium text-gray-800">{medication.medication}</div>
                            {medication.dosage && (
                              <p className="text-sm text-gray-600 mt-1">
                                <span className="font-medium">Dosage:</span> {medication.dosage}
                              </p>
                            )}
                            {medication.frequency && (
                              <p className="text-sm text-gray-600">
                                <span className="font-medium">Frequency:</span> {medication.frequency}
                              </p>
                            )}
                            {medication.purpose && (
                              <p className="text-sm text-gray-600">
                                <span className="font-medium">Purpose:</span> {medication.purpose}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {progressSummary.dietInformation && (
                    <div>
                      <h4 className="font-semibold text-gray-800 mb-2">{t('evaluation.dietInformation')}</h4>
                      <p className="text-gray-700">{progressSummary.dietInformation}</p>
                    </div>
                  )}

                  {progressSummary.habits && progressSummary.habits.length > 0 && (
                    <div>
                      <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.habits')}</h4>
                      <div className="space-y-2">
                        {progressSummary.habits.map((habit, index: number) => (
                          <div key={index} className="bg-white rounded p-3 border border-green-200">
                            <div className="font-medium text-gray-800">{habit.habit}</div>
                            {habit.duration && (
                              <p className="text-sm text-gray-600 mt-1">
                                <span className="font-medium">Duration:</span> {habit.duration}
                              </p>
                            )}
                            {habit.frequency && (
                              <p className="text-sm text-gray-600">
                                <span className="font-medium">Frequency:</span> {habit.frequency}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {progressSummary.workInformation && (
                    <div>
                      <h4 className="font-semibold text-gray-800 mb-2">{t('evaluation.workInformation')}</h4>
                      <p className="text-gray-700">{progressSummary.workInformation}</p>
                    </div>
                  )}

                  {progressSummary.medicalHistory && progressSummary.medicalHistory.length > 0 && (
                    <div>
                      <h4 className="font-semibold text-gray-800 mb-2">{t('evaluation.medicalHistory')}</h4>
                      <div className="space-y-2">
                        {progressSummary.medicalHistory.map((history, index: number) => (
                          <div key={index} className="bg-white rounded p-3 border border-green-200">
                            <div className="font-medium text-gray-800">{history.type}</div>
                            {history.date && (
                              <p className="text-sm text-gray-600 mt-1">
                                <span className="font-medium">Date:</span> {history.date}
                              </p>
                            )}
                            {history.description && (
                              <p className="text-sm text-gray-600">
                                <span className="font-medium">Description:</span> {history.description}
                              </p>
                            )}
                            {history.outcome && (
                              <p className="text-sm text-gray-600">
                                <span className="font-medium">Outcome:</span> {history.outcome}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {progressSummary.familyHistory && progressSummary.familyHistory.length > 0 && (
                    <div>
                      <h4 className="font-semibold text-gray-800 mb-2">{t('createCase.familyHistory')}</h4>
                      <div className="space-y-2">
                        {progressSummary.familyHistory.map((history, index: number) => (
                          <div key={index} className="bg-white rounded p-3 border border-green-200">
                            <div className="font-medium text-gray-800">{history.condition}</div>
                            {history.relationship && (
                              <p className="text-sm text-gray-600 mt-1">
                                <span className="font-medium">Relationship:</span> {history.relationship}
                              </p>
                            )}
                            {history.notes && (
                              <p className="text-sm text-gray-600">
                                <span className="font-medium">Notes:</span> {history.notes}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Clinical Hypotheses */}
                  {hypotheses && hypotheses.length > 0 && (
                    <div>
                      <h4 className="font-semibold text-gray-800 mb-2">{t('clinicalChat.clinicalHypotheses')}</h4>
                      <div className="space-y-3">
                        {hypotheses
                          .sort((a, b) => a.hypothesisOrder - b.hypothesisOrder)
                          .map((hypothesis) => (
                            <div key={hypothesis.id} className="bg-white rounded p-4 border border-green-200">
                              <div className="flex items-start gap-3">
                                <span className="flex-shrink-0 w-6 h-6 bg-green-600 text-white rounded-full flex items-center justify-center text-sm font-medium">
                                  {hypothesis.hypothesisOrder}
                                </span>
                                <p className="text-gray-700 leading-relaxed">{hypothesis.hypothesisText}</p>
                              </div>
                            </div>
                          ))}
                      </div>
                    </div>
                  )}

                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
};
