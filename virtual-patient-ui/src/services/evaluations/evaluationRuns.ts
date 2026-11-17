import {apiFetch} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';
import {EvaluationCondition, EvaluationResult} from '../../types/evaluation';
import {transformToCamelCase} from '../../utils/apiTransform';

export type EvaluationPromptMessage = {role: string; content: unknown};
export type EvaluationPromptCall = {
  aspect: string;
  promptMessages?: EvaluationPromptMessage[];
  systemPromptSha256?: string;
};
export type EvaluationRun = {
  condition: EvaluationCondition;
  createdAt: string;
  snapshot: {
    inputs?: {
      prompts?: Record<string, string>;
      fallbackPrompts?: Record<string, string>;
      availableAspects?: string[];
      fallbackPromptMessages?: EvaluationPromptCall[];
    };
    providerResponses?: EvaluationPromptCall[];
    output?: {evaluationResults?: EvaluationResult[]};
  };
};

export const getEvaluationRuns = async (interviewId: number): Promise<EvaluationRun[]> => {
  const response = await apiFetch(`${API_URL}/medical-interviews/${interviewId}/evaluation/runs`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error('Failed to load evaluation prompts');
  return transformToCamelCase(await response.json()) as EvaluationRun[];
};
