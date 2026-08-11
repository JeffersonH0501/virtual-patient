import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

export type CompletedCasesResponse = {
  user_id: number;
  completed_cases_count: number;
};

export type AverageDurationResponse = {
  user_id: number;
  average_duration_seconds: number;
  total_completed_cases: number;
  has_data: boolean;
};

export type AverageScoreResponse = {
  user_id: number;
  average_score: number;
  total_evaluations: number;
  has_data: boolean;
};

export type PersonalStatistics = {
  completedCases: number;
  averageDurationSeconds: number;
  averageScore: number;
  totalCompletedCases: number;
  totalEvaluations: number;
  hasDurationData: boolean;
  hasScoreData: boolean;
};

export const getCompletedCases = async (): Promise<CompletedCasesResponse> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/my/completed-cases`, {
    method: 'GET',
    headers: {
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch completed cases');
  }

  return response.json();
};

export const getAverageDuration = async (): Promise<AverageDurationResponse> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/my/average-duration`, {
    method: 'GET',
    headers: {
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch average duration');
  }

  return response.json();
};

export const getAverageScore = async (): Promise<AverageScoreResponse> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/my/average-score`, {
    method: 'GET',
    headers: {
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch average score');
  }

  return response.json();
};

export const getPersonalStatistics = async (): Promise<PersonalStatistics> => {
  try {
    const [completedCasesData, averageDurationData, averageScoreData] = await Promise.all([
      getCompletedCases(),
      getAverageDuration(),
      getAverageScore(),
    ]);

    return {
      completedCases: completedCasesData.completed_cases_count,
      averageDurationSeconds: averageDurationData.average_duration_seconds,
      averageScore: averageScoreData.average_score,
      totalCompletedCases: averageDurationData.total_completed_cases,
      totalEvaluations: averageScoreData.total_evaluations,
      hasDurationData: averageDurationData.has_data,
      hasScoreData: averageScoreData.has_data,
    };
  } catch (error) {
    console.error('Error fetching personal statistics:', error);
    // Return default values on error
    return {
      completedCases: 0,
      averageDurationSeconds: 0,
      averageScore: 0,
      totalCompletedCases: 0,
      totalEvaluations: 0,
      hasDurationData: false,
      hasScoreData: false,
    };
  }
};
