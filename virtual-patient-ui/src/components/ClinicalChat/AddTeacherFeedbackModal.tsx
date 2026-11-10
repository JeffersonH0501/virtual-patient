import {Dialog} from '../common/Dialog';
import {FC, useState, useEffect, useRef, useId} from 'react';
import {useTranslation} from 'react-i18next';
import {createTeacherFeedback, updateTeacherFeedback} from '../../services/teacherFeedback';
import {
  CreateTeacherFeedbackRequest,
  UpdateTeacherFeedbackRequest,
  TeacherFeedback,
} from '../../types/teacherFeedback';

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
  const {t} = useTranslation();
  const feedbackId = useId();
  const [newFeedback, setNewFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submitting = useRef(false);
  const hasChanges = !editingFeedback || newFeedback.trim() !== editingFeedback.feedback.trim();

  // Initialize feedback content when editing
  useEffect(() => {
    if (editingFeedback) {
      setNewFeedback(editingFeedback.feedback);
    } else {
      setNewFeedback('');
    }
  }, [editingFeedback]);

  const handleSaveFeedback = async () => {
    if (!newFeedback.trim() || !hasChanges || submitting.current) return;

    try {
      submitting.current = true;
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
      submitting.current = false;
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setNewFeedback('');
    onClose();
  };

  return (
    <Dialog
      title={
        editingFeedback
          ? t('clinicalChat.editTeacherFeedback')
          : t('clinicalChat.addTeacherFeedback')
      }
      open={isOpen}
      onClose={handleClose}
      busy={isSubmitting}
      containerId="add-teacher-feedback-modal"
      hasDismissAction
      actions={
        <>
          <button
            type="button"
            disabled={isSubmitting}
            onClick={handleClose}
            className="ui-button ui-button--secondary"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            onClick={handleSaveFeedback}
            disabled={!newFeedback.trim() || !hasChanges || isSubmitting}
            className="ui-button ui-button--primary"
          >
            {isSubmitting
              ? t('common.loading')
              : editingFeedback
                ? t('clinicalChat.updateFeedback')
                : t('clinicalChat.saveFeedback')}
          </button>
        </>
      }
    >
      <div className="space-y-layout">
        <div className="ui-field">
          <label htmlFor={feedbackId} className="ui-field-label">{t('clinicalChat.addFeedbackPrompt')}</label>
          <textarea
            id={feedbackId}
            disabled={isSubmitting}
            value={newFeedback}
            onChange={(e) => setNewFeedback(e.target.value)}
            placeholder={t('clinicalChat.teacherFeedbackPlaceholder')}
            className="ui-textarea resize-none"
            rows={6}
          />
        </div>
      </div>
    </Dialog>
  );
};
