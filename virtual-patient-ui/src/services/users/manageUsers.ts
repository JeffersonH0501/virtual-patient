import {LIST_PAGE_SIZE} from '../../utils/pagination';
import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {transformToCamelCase} from '../../utils/apiTransform';
import {User} from '../../types/user';

export type ManagedUserPayload = {
  name: string;
  email: string;
  password: string;
  role: 'student' | 'teacher';
};
export type ManagedUserUpdate = Partial<ManagedUserPayload>;
export type ManagedUsersPage = {users: User[]; total: number};
export const MANAGED_USERS_PAGE_SIZE = LIST_PAGE_SIZE;

const requestManagedUsers = async (
  path: string,
  method = 'GET',
  payload?: ManagedUserUpdate,
): Promise<Response> => {
  const response = await apiFetch(API_URL + '/users/admin' + path, {
    method,
    headers: {...getAuthHeaders(), 'Content-Type': 'application/json'},
    ...(payload ? {body: JSON.stringify(payload)} : {}),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (response.status === 409 || body.detail === 'Email already registered') {
      throw new Error('users.errors.duplicate');
    }
    if (response.status === 404) throw new Error('users.errors.notFound');
    if (response.status === 403) throw new Error('users.errors.forbidden');
    if (response.status === 422) throw new Error('users.errors.invalid');
    throw new Error('errors.generic');
  }
  return response;
};
export const listManagedUsers = async (offset = 0, limit = MANAGED_USERS_PAGE_SIZE): Promise<ManagedUsersPage> => {
  const response = await requestManagedUsers(
    '?offset=' + offset + '&limit=' + limit,
  );
  const header = response.headers.get('X-Total-Count');
  const total = Number(header);
  if (header === null || !Number.isSafeInteger(total) || total < 0) {
    throw new Error('errors.generic');
  }
  return {users: transformToCamelCase(await response.json()) as User[], total};
};
export const createManagedUser = async (payload: ManagedUserPayload): Promise<User> =>
  transformToCamelCase(await (await requestManagedUsers('', 'POST', payload)).json()) as User;
export const updateManagedUser = async (id: number, payload: ManagedUserUpdate): Promise<User> =>
  transformToCamelCase(
    await (await requestManagedUsers('/' + id, 'PATCH', payload)).json(),
  ) as User;
