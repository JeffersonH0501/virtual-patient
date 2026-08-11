import { transformToCamelCase } from '../../utils/apiTransform';
import { API_URL } from '../../utils/request';
import { getAuthHeaders } from '../auth/authHeaders';
import { TeacherFeedback, UpdateTeacherFeedbackRequest } from '../../types/teacherFeedback';

export const updateTeacherFeedback = async (
  interviewId: number,
  feedbackId: string,
  feedback: UpdateTeacherFeedbackRequest
): Promise<TeacherFeedback> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/${interviewId}/teacher-feedback/${feedbackId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
    body: JSON.stringify(feedback),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to update teacher feedback');
  }

  const data = await response.json();
  return transformToCamelCase(data) as TeacherFeedback;
};
