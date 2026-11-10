import {LIST_PAGE_SIZE} from '../../utils/pagination';
import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {OrganizationInterview} from '../../types/interview';

export const getOrganizationInterviews = async (
  organizationId: string,
  skip = 0,
  limit = LIST_PAGE_SIZE,
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
    },
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch organization interviews');
  }

  const data = await response.json();
  const total = Number(response.headers.get('X-Total-Count'));
  if (!response.headers.has('X-Total-Count') || !Number.isInteger(total) || total < 0) {
    throw new Error('errors.generic');
  }
  return {
    interviews: transformToCamelCase(data) as OrganizationInterview[],
    total,
  };
};
