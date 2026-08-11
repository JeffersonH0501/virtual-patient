import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

export type Organization = {
  id: string;
  name: string;
  description: string;
  active: boolean;
};

export type CreateOrganizationPayload = Omit<Organization, 'id'>;

export type UpdateOrganizationPayload = Partial<CreateOrganizationPayload>;

export async function createOrganization(payload: CreateOrganizationPayload) {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/organizations`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to create organization');
  }

  return response.json();
}

export async function getOrganizations(skip = 0, limit = 100) {
  const authHeaders = getAuthHeaders();
  const response = await fetch(
    `${API_URL}/organizations?skip=${skip}&limit=${limit}`,
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
    throw new Error(errorData.detail || 'Failed to fetch organizations');
  }

  return response.json();
}

export async function getOrganizationById(organizationId: string) {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/organizations/${organizationId}`, {
    method: 'GET',
    headers: {
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch organization');
  }

  return response.json();
}

export async function updateOrganization(
  organizationId: string,
  payload: UpdateOrganizationPayload
) {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/organizations/${organizationId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to update organization');
  }

  return response.json();
}

export async function deleteOrganization(organizationId: string) {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/organizations/${organizationId}`, {
    method: 'DELETE',
    headers: {
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to delete organization');
  }

  return response.json();
} 