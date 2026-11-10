import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {Users} from './index';

const mocks = vi.hoisted(() => ({
  role: 'superuser',
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
}));
const translate = (
  key: string,
  options?: {name?: string; page?: number; from?: number; to?: number; total?: number},
) =>
  key === 'pagination.showingUsers'
    ? 'Mostrando ' + options?.from + '-' + options?.to + ' de ' + options?.total + ' usuarios'
    : key + (options?.name ? ' ' + options.name : options?.page ? ' ' + options.page : '');
vi.mock('react-i18next', () => ({useTranslation: () => ({t: translate})}));
vi.mock('../../hooks/useUser', () => ({
  useUser: () => ({user: {role: mocks.role}, isLoading: false}),
}));
vi.mock('../../services/users/manageUsers', () => ({
  listManagedUsers: mocks.list,
  createManagedUser: mocks.create,
  updateManagedUser: mocks.update,
  MANAGED_USERS_PAGE_SIZE: 10,
}));
const account = {
  id: 1,
  name: 'Student',
  createdAt: '2026-10-20T14:00:00Z',
  email: 'student@example.org',
  role: 'student',
  preferredLanguage: 'es',
};
const renderUsers = () =>
  render(
    <MemoryRouter>
      <Users />
    </MemoryRouter>,
  );
const fill = (label: string, value: string) => {
  const control = screen.getByLabelText(label);
  if (control.getAttribute('role') === 'combobox') {
    fireEvent.click(control);
    fireEvent.click(screen.getByRole('option', {name: 'auth.' + value}));
  } else fireEvent.change(control, {target: {value}});
};
beforeEach(() => {
  mocks.list.mockReset().mockResolvedValue({users: [account], total: 1});
  mocks.create.mockReset().mockResolvedValue(account);
  mocks.update.mockReset().mockResolvedValue(account);
});
afterEach(() => {
  cleanup();
  mocks.role = 'superuser';
});

describe('account administration', () => {
  it('creates a teacher with one password without replacing the administrator session', async () => {
    renderUsers();
    await screen.findByText(account.email);
    fireEvent.click(screen.getByRole('button', {name: 'users.create'}));
    expect(screen.queryByLabelText('auth.confirmPassword')).toBeNull();
    fill('auth.name', 'Teacher');
    fill('auth.email', 'teacher@example.org');
    fill('auth.password', 'password');
    expect(screen.getByRole('combobox', {name: 'auth.role'}).textContent).toContain('users.selectRole');
    expect((screen.getByRole('button', {name: 'users.createAction'}) as HTMLButtonElement).disabled).toBe(true);
    fill('auth.role', 'teacher');
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'users.createAction'}));
    await waitFor(() =>
      expect(mocks.create).toHaveBeenCalledWith({
        name: 'Teacher',
        email: 'teacher@example.org',
        password: 'password',
        role: 'teacher',
      }),
    );
    await screen.findByText('users.created');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mocks.list).toHaveBeenLastCalledWith(0, 100);
  });
  it('preloads an account and preserves its password when the new password is empty', async () => {
    renderUsers();
    fireEvent.click(await screen.findByRole('row', {name: 'users.editAccount Student'}));
    expect((screen.getByLabelText('auth.name') as HTMLInputElement).value).toBe(account.name);
    expect((screen.getByLabelText('auth.password') as HTMLInputElement).value).toBe('');
    expect(screen.getByText('users.passwordHint')).toBeDefined();
    fill('auth.name', 'Updated');
    fill('auth.email', 'updated@example.org');
    fill('auth.role', 'teacher');
    fireEvent.click(screen.getByRole('button', {name: 'users.save'}));
    await waitFor(() =>
      expect(mocks.update).toHaveBeenCalledWith(1, {
        name: 'Updated',
        email: 'updated@example.org',
        role: 'teacher',
      }),
    );
    await screen.findByText('users.updated');
  });
  it('sends a new password only when entered and supports showing it', async () => {
    renderUsers();
    fireEvent.click(await screen.findByRole('row', {name: 'users.editAccount Student'}));
    fill('auth.password', 'replacement');
    fireEvent.click(screen.getByRole('button', {name: 'auth.showPassword'}));
    expect((screen.getByLabelText('auth.password') as HTMLInputElement).type).toBe('text');
    fireEvent.click(screen.getByRole('button', {name: 'users.save'}));
    await waitFor(() =>
      expect(mocks.update).toHaveBeenCalledWith(
        1,
        expect.objectContaining({password: 'replacement'}),
      ),
    );
  });
  it('retains form values after an error and clears passwords after cancellation', async () => {
    mocks.update.mockRejectedValueOnce(new Error('users.errors.duplicate'));
    renderUsers();
    fireEvent.click(await screen.findByRole('row', {name: 'users.editAccount Student'}));
    fill('auth.password', 'replacement');
    fill('auth.email', 'duplicate@example.org');
    fireEvent.click(screen.getByRole('button', {name: 'users.save'}));
    await screen.findByRole('alert');
    expect((screen.getByLabelText('auth.email') as HTMLInputElement).value).toBe(
      'duplicate@example.org',
    );
    fireEvent.click(screen.getByRole('button', {name: 'common.cancel'}));
    fireEvent.click(screen.getByRole('row', {name: 'users.editAccount Student'}));
    expect((screen.getByLabelText('auth.password') as HTMLInputElement).value).toBe('');
  });
  it('blocks repeated submits and cancellation while saving', async () => {
    let finish: (value: typeof account) => void = () => undefined;
    mocks.update.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    renderUsers();
    fireEvent.click(await screen.findByRole('row', {name: 'users.editAccount Student'}));
    fill('auth.name', 'Changed name');
    const form = screen.getByRole('dialog').querySelector('form')!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(mocks.update).toHaveBeenCalledTimes(1);
    expect(
      (screen.getByRole('button', {name: 'common.cancel'}) as HTMLButtonElement).disabled,
    ).toBe(true);
    finish(account);
    await screen.findByText('users.updated');
  });
  it('distinguishes loading failures and retries', async () => {
    mocks.list.mockRejectedValueOnce(new Error('errors.generic'));
    renderUsers();
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', {name: 'common.retry'}));
    await screen.findByText(account.email);
    expect(mocks.list).toHaveBeenCalledTimes(2);
  });
  it('shows exact user ranges and the server total on every page', async () => {
    mocks.list
      .mockResolvedValueOnce({
        users: Array.from({length: 11}, (_, index) => ({...account, id: index + 1})),
        total: 11,
      });
    renderUsers();
    await screen.findByText('Mostrando 1-10 de 11 usuarios');
    fireEvent.click(screen.getByRole('button', {name: 'common.next'}));
    await screen.findByText('Mostrando 11-11 de 11 usuarios');
    expect(mocks.list).toHaveBeenCalledExactlyOnceWith(0, 100);
    expect((screen.getByRole('button', {name: 'common.next'}) as HTMLButtonElement).disabled).toBe(
      true,
    );
    fireEvent.click(screen.getByRole('button', {name: 'common.previous'}));
    await screen.findByText('Mostrando 1-10 de 11 usuarios');
    expect(mocks.list).toHaveBeenCalledExactlyOnceWith(0, 100);
  });
  it('shows a zero range for an empty organization', async () => {
    mocks.list.mockResolvedValueOnce({users: [], total: 0});
    renderUsers();
    await screen.findByText('users.empty');
    expect(screen.getByText('Mostrando 0-0 de 0 usuarios')).toBeDefined();
    expect((screen.getByRole('button', {name: 'common.next'}) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
  it.each(['student', 'teacher'])('does not load accounts for %s', (role) => {
    mocks.role = role;
    renderUsers();
    expect(mocks.list).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('auth.role')).toBeNull();
  });
});

it('shows registration date first and places creation beside the single page heading', async () => {
  renderUsers();
  await screen.findByText(account.email);
  const table = screen.getByRole('table');
  expect(screen.getAllByRole('columnheader')[0].textContent).toBe('users.registeredAt');
  expect(table.querySelector('time')?.getAttribute('datetime')).toBe(account.createdAt);
  expect(table.querySelector('caption')?.textContent).toBe('users.accounts');
  expect(screen.queryByText('users.tableCaption')).toBeNull();
  expect(screen.queryByRole('heading', {name: 'navigation.users'})).toBeNull();
  const create = screen.getByRole('button', {name: 'users.create'});
  expect(create.closest('header')?.textContent).toContain('users.pageTitle');
  expect(create.closest('.ui-button-group--large')).not.toBeNull();
});
it('does not invent registration dates for legacy accounts', async () => {
  mocks.list.mockResolvedValueOnce({users: [{...account, createdAt: null}], total: 1});
  renderUsers();
  await screen.findByText('users.dateUnavailable');
  expect(screen.getByRole('table').querySelector('time')).toBeNull();
});

it('enables saving only for meaningful changes and disables again when reverted', async () => {
  renderUsers();
  fireEvent.click(await screen.findByRole('row', {name: 'users.editAccount Student'}));
  const save = () => screen.getByRole('button', {name: 'users.save'}) as HTMLButtonElement;
  const form = screen.getByRole('dialog').querySelector('form')!;
  expect(save().disabled).toBe(true);
  expect(screen.queryByLabelText('users.newPassword')).toBeNull();
  fireEvent.submit(form);
  expect(mocks.update).not.toHaveBeenCalled();
  fill('auth.name', 'Changed');
  expect(save().disabled).toBe(false);
  fill('auth.name', account.name);
  expect(save().disabled).toBe(true);
  fill('auth.email', 'STUDENT@example.org');
  expect(save().disabled).toBe(true);
  fill('auth.email', account.email);
  fill('auth.role', 'teacher');
  expect(save().disabled).toBe(false);
  fill('auth.role', 'student');
  expect(save().disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', {name: 'auth.showPassword'}));
  expect(save().disabled).toBe(true);
  fill('auth.password', 'replacement');
  expect(save().disabled).toBe(false);
  fill('auth.password', '');
  expect(save().disabled).toBe(true);
});
it('keeps invalid changes disabled and sends only changed fields after correction', async () => {
  renderUsers();
  fireEvent.click(await screen.findByRole('row', {name: 'users.editAccount Student'}));
  const save = () => screen.getByRole('button', {name: 'users.save'}) as HTMLButtonElement;
  fill('auth.name', 'Changed');
  fill('auth.email', 'invalid');
  expect(save().disabled).toBe(true);
  fill('auth.email', account.email);
  fill('auth.password', '   ');
  expect(save().disabled).toBe(true);
  fill('auth.password', '');
  expect(save().disabled).toBe(false);
  fireEvent.click(save());
  await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(1, {name: 'Changed'}));
});




it('opens account editing from the row keyboard and keeps delete separate', async () => {
  renderUsers();
  const row = await screen.findByRole('row', {name: 'users.editAccount Student'});
  expect(screen.queryByRole('button', {name: 'users.editAccount Student'})).toBeNull();
  fireEvent.keyDown(row, {key: ' '});
  expect(screen.getByLabelText('auth.name')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'common.cancel'}));
  fireEvent.click(within(row).getByRole('button', {name: 'common.delete'}));
  expect(screen.queryByLabelText('auth.name')).toBeNull();
  expect(screen.getByRole('dialog')).toBeTruthy();
});
