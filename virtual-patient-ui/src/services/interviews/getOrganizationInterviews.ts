import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {OrganizationInterview} from '../../types/interview';

export const getOrganizationInterviews = async (
  organizationId: string,
  skip = 0,
  limit = 100
) => {
  const authHeaders = getAuthHeaders();
  const params = new URLSearchParams({
    skip: skip.toString(),
    limit: limit.toString(),
  });
  
  const response = await apiFetch(
    `${API_URL}/medical-interviews/organization/${organizationId}?${params.toString()}`,
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
    throw new Error(errorData.detail || 'Failed to fetch organization interviews');
  }

  const data = await response.json();
  return transformToCamelCase(data) as OrganizationInterview[];
};
