import { FC, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../common/Modal';
import { getTeacherFeedbacks } from '../../services/teacherFeedback';
import { TeacherFeedback } from '../../types/teacherFeedback';
import { useUser } from '../../hooks/useUser';
import { AddTeacherFeedbackModal } from './AddTeacherFeedbackModal';
import { Button } from '../common/Button';
import {EditIcon, X} from '../../icons';

type TeacherFeedbackSectionProps = {
  interviewId: number;
};

export const TeacherFeedbackSection: FC<TeacherFeedbackSectionProps> = ({ interviewId }) => {
  const { t } = useTranslation();
  const { user } = useUser();
  const [feedbacks, setFeedbacks] = useState<TeacherFeedback[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFeedback, setSelectedFeedback] = useState<TeacherFeedback | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingFeedback, setEditingFeedback] = useState<TeacherFeedback | null>(null);

  useEffect(() => {
    const fetchFeedbacks = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await getTeacherFeedbacks(interviewId);
        setFeedbacks(data);
      } catch (err) {
        setError(t('clinicalChat.errorLoadingFeedback'));
        console.error('Error fetching teacher feedbacks:', err);
      } finally {
        setLoading(false);
      }
    };

    if (interviewId) {
      fetchFeedbacks();
    }
  }, [interviewId, t]);

  const handleFeedbackClick = (feedback: TeacherFeedback) => {
    setSelectedFeedback(feedback);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedFeedback(null);
  };

  const openAddModal = () => {
    setIsAddModalOpen(true);
  };

  const closeAddModal = () => {
    setIsAddModalOpen(false);
    setEditingFeedback(null);
  };

  const handleFeedbackAdded = (feedback: TeacherFeedback) => {
    if (editingFeedback) {
      // Update existing feedback
      setFeedbacks(prev => prev.map(f => f.id === feedback.id ? feedback : f));
    } else {
      // Add new feedback
      setFeedbacks(prev => [...prev, feedback]);
    }
  };

  if (loading) {
    return (
      <section className="overflow-hidden rounded-xl bg-white shadow-panel-subtle">
        <h3 className="component-title flex min-h-12 items-center border-b border-slate-200 px-4 text-left">
          {t('clinicalChat.teacherFeedback')}
        </h3>
        <p className="p-4 text-center text-sm text-gray-500">
          Loading...
        </p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="overflow-hidden rounded-xl bg-white shadow-panel-subtle">
        <h3 className="component-title flex min-h-12 items-center border-b border-slate-200 px-4 text-left">
          {t('clinicalChat.teacherFeedback')}
        </h3>
        <p className="p-4 text-center text-sm text-red-500">
          {error}
        </p>
      </section>
    );
  }

  if (feedbacks.length === 0) {
    return (
      <section className="overflow-hidden rounded-xl bg-white shadow-panel-subtle">
        <div className="flex min-h-12 items-center justify-between gap-3 border-b border-slate-200 px-4">
          <h3 className="component-title text-left">
            {t('clinicalChat.teacherFeedback')}
          </h3>
          {(user?.role === 'teacher' || user?.role === 'superuser') && (
            <Button
              onClick={openAddModal}
              variant="primary"
              size="sm"
            >
              {t('clinicalChat.addTeacherFeedback')}
            </Button>
          )}
        </div>
        <p className="p-4 text-center text-sm text-gray-500">
          {t('clinicalChat.noFeedbackYet')}
        </p>
        <AddTeacherFeedbackModal
        isOpen={isAddModalOpen}
        onClose={closeAddModal}
        interviewId={interviewId}
        onFeedbackAdded={handleFeedbackAdded}
        editingFeedback={editingFeedback}
      />
      </section>
    );
  }

  return (
    <>
      <section className="overflow-hidden rounded-xl bg-white shadow-panel-subtle">
        <div className="flex min-h-12 items-center justify-between gap-3 border-b border-slate-200 px-4">
          <h3 className="component-title text-left">
            {t('clinicalChat.teacherFeedback')}
          </h3>
          {(user?.role === 'teacher' || user?.role === 'superuser') && (
            <Button
              onClick={openAddModal}
              variant="primary"
              size="sm"
            >
              {t('clinicalChat.addTeacherFeedback')}
            </Button>
          )}
        </div>
        <div className="space-y-3 p-4">
          {feedbacks.map((feedback) => (
            <div
              key={feedback.id}
              onClick={() => handleFeedbackClick(feedback)}
              className="p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                    <span className="text-xs font-medium text-blue-600">
                      T
                    </span>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {feedback.teacherName || `Teacher ${feedback.teacherId}`}
                    </p>
                    <p className="text-xs text-gray-500">
                      {new Date(feedback.createdAt).toLocaleDateString('en-US', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </p>
                  </div>
                </div>
                <div className="text-xs text-gray-400">
                  {t('clinicalChat.clickToView')}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Teacher Feedback Modal */}
      {selectedFeedback && (
        <Modal open={isModalOpen} closeAction={closeModal} size="medium" containerId="teacher-feedback-modal">
          <div className="dialog-shell">
            <div className="dialog-header">
              <h2 className="dialog-title">
                {t('clinicalChat.teacherFeedback')}
              </h2>
              <button
                onClick={closeModal}
                className="dialog-close-button"
                aria-label={t('common.close')}
                title={t('common.close')}
              >
                <span className="block h-6 w-6 [&_svg]:h-full [&_svg]:w-full"><X color="currentColor" /></span>
              </button>
            </div>

            <div className="dialog-content flex-1">
              <div className="space-y-6">
                {/* Teacher Info */}
                <div className="flex items-center gap-3 pb-4">
                  <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                    <span className="text-lg font-medium text-blue-600">
                      T
                    </span>
                  </div>
                  <div>
                    <p className="text-lg font-semibold text-gray-900">
                      {selectedFeedback.teacherName || `Teacher ${selectedFeedback.teacherId}`}
                    </p>
                    <p className="text-sm text-gray-500">
                      {new Date(selectedFeedback.createdAt).toLocaleDateString('en-US', {
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </p>
                  </div>
                </div>

                {/* Feedback Content */}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-md font-semibold text-gray-800">
                      {t('clinicalChat.feedbackContent')}
                    </h3>
                    {(user?.role === 'teacher' || user?.role === 'superuser') && selectedFeedback.reviewedByYou && (
                      <button
                        onClick={() => {
                          setEditingFeedback(selectedFeedback);
                          closeModal();
                          setIsAddModalOpen(true);
                        }}
                        className="flex items-center justify-center p-2 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-lg transition-colors"
                        title={t('clinicalChat.editTeacherFeedback')}
                      >
                        <span className="block h-4 w-4 [&_svg]:h-full [&_svg]:w-full"><EditIcon color="currentColor" /></span>
                      </button>
                    )}
                  </div>
                  <div className="p-4 bg-gray-50 rounded-lg">
                    <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                      {selectedFeedback.feedback}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Modal>
      )}

      <AddTeacherFeedbackModal
        isOpen={isAddModalOpen}
        onClose={closeAddModal}
        interviewId={interviewId}
        onFeedbackAdded={handleFeedbackAdded}
        editingFeedback={editingFeedback}
      />
    </>
  );
};

