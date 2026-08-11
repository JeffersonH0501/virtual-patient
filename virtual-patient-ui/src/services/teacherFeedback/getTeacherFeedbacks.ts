import { transformToCamelCase } from '../../utils/apiTransform';
import { API_URL } from '../../utils/request';
import { getAuthHeaders } from '../auth/authHeaders';
import { TeacherFeedback } from '../../types/teacherFeedback';

export const getTeacherFeedbacks = async (interviewId: number): Promise<TeacherFeedback[]> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/${interviewId}/teacher-feedback`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch teacher feedbacks');
  }

  const data = await response.json();
  return data.map((item: any) => transformToCamelCase(item) as TeacherFeedback);
};
