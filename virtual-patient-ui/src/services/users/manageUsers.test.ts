import {beforeEach, expect, it, vi} from 'vitest';
import {createManagedUser, listManagedUsers, updateManagedUser} from './manageUsers';
const mocks = vi.hoisted(() => ({fetch: vi.fn()}));
vi.mock('../../utils/apiFetch', () => ({apiFetch: mocks.fetch}));
vi.mock('../auth/authHeaders', () => ({
  getAuthHeaders: () => ({Authorization: 'Bearer test-session'}),
}));
const account = {
  id: 2,
  name: 'Teacher',
  email: 'teacher@example.org',
  role: 'teacher',
  preferred_language: 'es',
};
beforeEach(() => mocks.fetch.mockReset());
it('lists a server page and transforms response keys', async () => {
  mocks.fetch.mockResolvedValue(
    new Response(JSON.stringify([account]), {headers: {'X-Total-Count': '101'}}),
  );
  expect(await listManagedUsers(100)).toEqual({
    total: 101,
    users: [
      {
        id: 2,
        name: 'Teacher',
        email: 'teacher@example.org',
        role: 'teacher',
        preferredLanguage: 'es',
      },
    ],
  });
  expect(mocks.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/users/admin?offset=100&limit=10'),
    expect.objectContaining({method: 'GET'}),
  );
});
it('creates an account while retaining the administrator authorization', async () => {
  mocks.fetch.mockResolvedValue(new Response(JSON.stringify(account), {status: 201}));
  const payload = {
    name: 'Teacher',
    email: account.email,
    password: 'password',
    role: 'teacher',
  } as const;
  expect((await createManagedUser(payload)).id).toBe(2);
  expect(mocks.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/users/admin'),
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify(payload),
      headers: expect.objectContaining({Authorization: 'Bearer test-session'}),
    }),
  );
});
it('patches only provided fields and leaves omitted passwords absent', async () => {
  mocks.fetch.mockResolvedValue(new Response(JSON.stringify(account)));
  await updateManagedUser(2, {name: 'Updated'});
  expect(mocks.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/users/admin/2'),
    expect.objectContaining({method: 'PATCH', body: JSON.stringify({name: 'Updated'})}),
  );
});
it.each([
  [409, 'duplicate'],
  [404, 'notFound'],
  [403, 'forbidden'],
  [422, 'invalid'],
])('maps HTTP %s to a localized error key', async (status, key) => {
  mocks.fetch.mockResolvedValue(new Response('{}', {status: Number(status)}));
  await expect(updateManagedUser(2, {name: 'Updated'})).rejects.toThrow('users.errors.' + key);
});

it('rejects a missing total instead of presenting a guessed user count', async () => {
  mocks.fetch.mockResolvedValue(new Response(JSON.stringify([account])));
  await expect(listManagedUsers()).rejects.toThrow('errors.generic');
});
