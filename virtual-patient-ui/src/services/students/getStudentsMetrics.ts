import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';

export type StudentsMetrics = {
  activeCount: number;
  completedCount: number;
  averageScore: number;
  hasData: boolean;
};

export const getStudentsMetrics = async (
  organizationId: string,
  countInterviews = false,
): Promise<StudentsMetrics> => {
  const getMetric = async (path: string) => {
    const response = await apiFetch(
      API_URL + '/medical-interviews/organization/' + organizationId + '/' + path,
      {headers: {accept: 'application/json', ...getAuthHeaders()}},
    );
    if (!response.ok) throw new Error('errors.generic');
    return response.json();
  };
  const [counts, average] = await Promise.all([
    countInterviews
      ? getMetric('interview-counts')
      : Promise.all([
          getMetric('active-students-count'),
          getMetric('completed-students-count'),
        ]).then(([active, completed]) => ({
          active_interviews_count: active.active_students_count,
          completed_interviews_count: completed.completed_students_count,
        })),
    getMetric('average-score'),
  ]);
  return {
    activeCount: counts.active_interviews_count,
    completedCount: counts.completed_interviews_count,
    averageScore: average.average_score ?? 0,
    hasData: average.has_data,
  };
};
