import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {useManagedUsers} from './useManagedUsers';
import {listManagedUsers} from '../../services/users/manageUsers';
import {User} from '../../types/user';

vi.mock('../../services/users/manageUsers', () => ({MANAGED_USERS_PAGE_SIZE: 5, listManagedUsers: vi.fn()}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const users = Array.from({length: 6}, (_, index) => ({id: index + 1} as User));

it('changes pages locally and clamps the page after deleting its last row', async () => {
  vi.mocked(listManagedUsers)
    .mockResolvedValueOnce({users, total: 6})
    .mockResolvedValueOnce({users: users.slice(0, 5), total: 5});
  const {result} = renderHook(() => useManagedUsers(true));
  await waitFor(() => expect(result.current.loading).toBe(false));
  act(() => result.current.setOffset(5));
  expect(result.current.users.map(({id}) => id)).toEqual([6]);
  expect(listManagedUsers).toHaveBeenCalledExactlyOnceWith(0, 100);
  act(() => result.current.reload());
  await waitFor(() => expect(result.current.offset).toBe(0));
  expect(result.current.users).toHaveLength(5);
});
