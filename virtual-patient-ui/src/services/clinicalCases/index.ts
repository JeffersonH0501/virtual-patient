import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {transformToCamelCase} from '../../utils/apiTransform';
import {ClinicalCaseBase} from '../../types/clinicalCase';

export type ClinicalCaseSimplified = ClinicalCaseBase;

export async function getDefaultCases(skip = 0, limit = 100) {
  const authHeaders = getAuthHeaders();
  const response = await apiFetch(
    `${API_URL}/clinical-cases/default?skip=${skip}&limit=${limit}`,
    {
      method: 'GET',
      headers: {
        accept: 'application/json',
        ...authHeaders,
      },
    },
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch default cases');
  }

  const data = await response.json();
  return transformToCamelCase(data) as ClinicalCaseSimplified[];
}

export async function getClinicalCaseById(caseId: string) {
  const authHeaders = getAuthHeaders();
  const response = await apiFetch(`${API_URL}/clinical-cases/${caseId}`, {
    method: 'GET',
    headers: {
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch clinical case');
  }

  const data = await response.json();
  return transformToCamelCase(data);
}

