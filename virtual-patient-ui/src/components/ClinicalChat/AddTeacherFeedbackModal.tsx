import { FC, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../common/Modal';
import { createTeacherFeedback, updateTeacherFeedback } from '../../services/teacherFeedback';
import { CreateTeacherFeedbackRequest, UpdateTeacherFeedbackRequest, TeacherFeedback } from '../../types/teacherFeedback';

type AddTeacherFeedbackModalProps = {
  isOpen: boolean;
  onClose: () => void;
  interviewId: number;
  onFeedbackAdded: (feedback: any) => void;
  editingFeedback?: TeacherFeedback | null; // Add optional editing feedback
};

export const AddTeacherFeedbackModal: FC<AddTeacherFeedbackModalProps> = ({
  isOpen,
  onClose,
  interviewId,
  onFeedbackAdded,
  editingFeedback,
}) => {
  const { t } = useTranslation();
  const [newFeedback, setNewFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Initialize feedback content when editing
  useEffect(() => {
    if (editingFeedback) {
      setNewFeedback(editingFeedback.feedback);
    } else {
      setNewFeedback('');
    }
  }, [editingFeedback]);

  const handleSaveFeedback = async () => {
    if (!newFeedback.trim()) return;

    try {
      setIsSubmitting(true);

      if (editingFeedback) {
        // Update existing feedback
        const updateData: UpdateTeacherFeedbackRequest = {
          feedback: newFeedback.trim(),
        };

        const updatedFeedback = await updateTeacherFeedback(
          interviewId,
          editingFeedback.id.toString(),
          updateData,
        );
        onFeedbackAdded(updatedFeedback);
      } else {
        // Create new feedback
        const feedbackData: CreateTeacherFeedbackRequest = {
          feedback: newFeedback.trim(),
        };

        const createdFeedback = await createTeacherFeedback(interviewId, feedbackData);
        onFeedbackAdded(createdFeedback);
      }

      handleClose();
    } catch (err) {
      console.error('Error saving teacher feedback:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setNewFeedback('');
    onClose();
  };

  return (
    <Modal open={isOpen} closeAction={handleClose} size="medium" containerId="add-teacher-feedback-modal" hasActions>
      <div className="flex flex-col h-full max-h-dialog-content rounded-2xl">
        <div className="border-b border-gray-200 bg-white p-4 rounded-t-2xl">
          <h2 className="text-lg font-semibold text-gray-800">
            {editingFeedback ? t('clinicalChat.editTeacherFeedback') : t('clinicalChat.addTeacherFeedback')}
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('clinicalChat.addFeedbackPrompt')}
              </label>
              <textarea
                value={newFeedback}
                onChange={(e) => setNewFeedback(e.target.value)}
                placeholder={t('clinicalChat.teacherFeedbackPlaceholder')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none text-gray-900"
                rows={6}
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end rounded-b-2xl bg-white p-4">
          <div className="dialog-actions">
            <button
              onClick={handleClose}
              className="dialog-action dialog-action--secondary"
            >
              {t('common.cancel')}
            </button>
            <button
              onClick={handleSaveFeedback}
              disabled={!newFeedback.trim() || isSubmitting}
              className="dialog-action dialog-action--primary"
            >
              {isSubmitting ? t('common.loading') : (editingFeedback ? t('clinicalChat.updateFeedback') : t('clinicalChat.saveFeedback'))}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
};
