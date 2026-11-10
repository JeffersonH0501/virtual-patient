import {apiFetch} from '../utils/apiFetch';
import {API_URL} from '../utils/request';
import {getAuthHeaders} from './auth/authHeaders';
import {transformToCamelCase} from '../utils/apiTransform';
import {EvaluationResult} from '../types/evaluation';

export type Assignment = {
  id: number;
  interviewId: number;
  teacherId: number;
  teacherName: string;
  teacherEmail?: string;
  status: 'pending' | 'in_progress' | 'submitted';
  studentName?: string;
  caseTitle?: string;
  personalityName?: string | null;
  totalDuration?: number | null;
  overallScore?: number | null;
  createdAt?: string;
};
export type Workspace = Pick<Assignment, 'id' | 'interviewId' | 'status'> & {
  rubric: Record<string, string[]>;
  results: {aspect: string; score: number | null; feedback: string}[];
  overallScore: number | null;
};
export type HumanRating = {
  id: number;
  teacherName: string;
  results: EvaluationResult[];
  overallScore: number;
  submittedAt: string;
};
export const gradingRequest = async <T>(
  path: string,
  method = 'GET',
  payload?: unknown,
): Promise<T> => {
  const response = await apiFetch(API_URL + path, {
    method,
    headers: {'Content-Type': 'application/json', ...getAuthHeaders()},
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (!response.ok) {
    const failure = await response.json().catch(() => ({}));
    throw new Error(failure.detail || 'Request failed');
  }
  if (response.status === 204) return undefined as T;
  const raw = await response.json();
  const converted = transformToCamelCase(raw);
  if (raw.rubric) converted.rubric = raw.rubric;
  return converted as T;
};

export type Reviewer = {assignmentId: number; teacherId: number; teacherName: string; status: Assignment['status']; ratingId: number | null};
