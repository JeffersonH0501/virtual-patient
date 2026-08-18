import { FC, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from '../common/Modal';
import { getTeacherFeedbacks } from '../../services/teacherFeedback';
import { TeacherFeedback } from '../../types/teacherFeedback';
import { useUser } from '../../hooks/useUser';
import { AddTeacherFeedbackModal } from './AddTeacherFeedbackModal';
import { Button } from '../common/Button';

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
      <section className="overflow-hidden rounded-xl bg-white shadow-[0_1px_2px_rgba(0,0,0,0.05)]">
        <h3 className="flex min-h-12 items-center border-b border-slate-200 px-4 text-left text-sm font-medium text-slate-600">
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
      <section className="overflow-hidden rounded-xl bg-white shadow-[0_1px_2px_rgba(0,0,0,0.05)]">
        <h3 className="flex min-h-12 items-center border-b border-slate-200 px-4 text-left text-sm font-medium text-slate-600">
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
      <section className="overflow-hidden rounded-xl bg-white shadow-[0_1px_2px_rgba(0,0,0,0.05)]">
        <div className="flex min-h-12 items-center justify-between gap-3 border-b border-slate-200 px-4">
          <h3 className="text-left text-sm font-medium text-slate-600">
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
      <section className="overflow-hidden rounded-xl bg-white shadow-[0_1px_2px_rgba(0,0,0,0.05)]">
        <div className="flex min-h-12 items-center justify-between gap-3 border-b border-slate-200 px-4">
          <h3 className="text-left text-sm font-medium text-slate-600">
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
                      {feedback.teacherUsername || `Teacher ${feedback.teacherId}`}
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
          <div className="flex flex-col h-full max-h-[80vh] rounded-2xl">
            <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-white rounded-t-2xl">
              <h2 className="text-lg font-semibold text-gray-800">
                {t('clinicalChat.teacherFeedback')}
              </h2>
              <button
                onClick={closeModal}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6">
              <div className="space-y-6">
                {/* Teacher Info */}
                <div className="flex items-center gap-3 pb-4 border-b border-gray-200">
                  <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                    <span className="text-lg font-medium text-blue-600">
                      T
                    </span>
                  </div>
                  <div>
                    <p className="text-lg font-semibold text-gray-900">
                      {selectedFeedback.teacherUsername || `Teacher ${selectedFeedback.teacherId}`}
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
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
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
