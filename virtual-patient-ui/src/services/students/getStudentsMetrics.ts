import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

export type StudentsMetrics = {
  activeStudentsCount: number;
  completedStudentsCount: number;
  averageScore: number;
  totalEvaluations: number;
  hasData: boolean;
};

export const getStudentsMetrics = async (organizationId: string): Promise<StudentsMetrics> => {
  const authHeaders = getAuthHeaders();
  
  try {
    // Fetch all three metrics in parallel
    const [activeStudentsResponse, completedStudentsResponse, averageScoreResponse] = await Promise.all([
      fetch(`${API_URL}/medical-interviews/organization/${organizationId}/active-students-count`, {
        method: 'GET',
        headers: {
          accept: 'application/json',
          ...authHeaders,
        },
      }),
      fetch(`${API_URL}/medical-interviews/organization/${organizationId}/completed-students-count`, {
        method: 'GET',
        headers: {
          accept: 'application/json',
          ...authHeaders,
        },
      }),
      fetch(`${API_URL}/medical-interviews/organization/${organizationId}/average-score`, {
        method: 'GET',
        headers: {
          accept: 'application/json',
          ...authHeaders,
        },
      }),
    ]);

    // Check if all requests were successful
    if (!activeStudentsResponse.ok || !completedStudentsResponse.ok || !averageScoreResponse.ok) {
      throw new Error('Failed to fetch students metrics');
    }

    // Parse responses
    const [activeStudentsData, completedStudentsData, averageScoreData] = await Promise.all([
      activeStudentsResponse.json(),
      completedStudentsResponse.json(),
      averageScoreResponse.json(),
    ]);

    return {
      activeStudentsCount: activeStudentsData.active_students_count || 0,
      completedStudentsCount: completedStudentsData.completed_students_count || 0,
      averageScore: averageScoreData.average_score || 0,
      totalEvaluations: averageScoreData.total_evaluations || 0,
      hasData: averageScoreData.has_data || false,
    };
  } catch (error) {
    console.error('Error fetching students metrics:', error);
    // Return default values on error
    return {
      activeStudentsCount: 0,
      completedStudentsCount: 0,
      averageScore: 0,
      totalEvaluations: 0,
      hasData: false,
    };
  }
};
