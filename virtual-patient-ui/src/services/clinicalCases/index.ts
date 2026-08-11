import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {transformToCamelCase, transformToSnakeCase} from '../../utils/apiTransform';
import {CaseType, ClinicalCaseBase, PatientFields} from '../../types/clinicalCase';

export type ClinicalCaseSimplified = ClinicalCaseBase;

export type CreateClinicalCasePayload = Omit<ClinicalCaseBase, 'id'> &
  PatientFields;

export type UpdateClinicalCasePayload = Partial<CreateClinicalCasePayload>;

export async function createClinicalCase(payload: CreateClinicalCasePayload) {
  const authHeaders = getAuthHeaders();
  const response = await apiFetch(`${API_URL}/clinical-cases`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
    body: JSON.stringify(transformToSnakeCase(payload)),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to create clinical case');
  }

  const data = await response.json();
  return transformToCamelCase(data);
}

export async function getClinicalCases(
  skip = 0,
  limit = 100,
  caseType?: CaseType,
  organizationId?: string
) {
  const authHeaders = getAuthHeaders();
  const params = new URLSearchParams({
    skip: skip.toString(),
    limit: limit.toString(),
    ...(caseType && {case_type: caseType}),
    ...(organizationId && {organization_id: organizationId}),
  });

  const response = await apiFetch(
    `${API_URL}/clinical-cases?${params.toString()}`,
    {
      method: 'GET',
      headers: {
        accept: 'application/json',
        ...authHeaders,
      },
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch clinical cases');
  }

  const data = await response.json();
  return transformToCamelCase(data);
}

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
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch default cases');
  }

  const data = await response.json();
  return transformToCamelCase(data);
}

export async function getCasesByOrganization(
  organizationId: string,
  skip = 0,
  limit = 100
) {
  const authHeaders = getAuthHeaders();
  const response = await apiFetch(
    `${API_URL}/clinical-cases/organization/${organizationId}?skip=${skip}&limit=${limit}`,
    {
      method: 'GET',
      headers: {
        accept: 'application/json',
        ...authHeaders,
      },
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch organization cases');
  }

  const data = await response.json();
  return transformToCamelCase(data);
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

export async function updateClinicalCase(
  caseId: string,
  payload: UpdateClinicalCasePayload
) {
  const authHeaders = getAuthHeaders();
  const response = await apiFetch(`${API_URL}/clinical-cases/${caseId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
    body: JSON.stringify(transformToSnakeCase(payload)),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to update clinical case');
  }

  const data = await response.json();
  return transformToCamelCase(data);
}

export async function deleteClinicalCase(caseId: string) {
  const authHeaders = getAuthHeaders();
  const response = await apiFetch(`${API_URL}/clinical-cases/${caseId}`, {
    method: 'DELETE',
    headers: {
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to delete clinical case');
  }

  const data = await response.json();
  return transformToCamelCase(data);
}