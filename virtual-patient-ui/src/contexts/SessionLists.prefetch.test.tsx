import {cleanup, render, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {SessionListsProvider} from './SessionLists';
import type {User} from '../types/user';

const reads = vi.hoisted(() => ({detail: vi.fn(), recap: vi.fn(), own: vi.fn(), organization: vi.fn(), request: vi.fn()}));
vi.mock('../services/interviews/getInterview', () => ({getInterview: reads.detail}));
vi.mock('../services/recordings', () => ({getInterviewRecap: reads.recap}));
vi.mock('../services/interviews/getInterviews', () => ({getInterviews: reads.own}));
vi.mock('../services/interviews/getOrganizationInterviews', () => ({getOrganizationInterviews: reads.organization}));
vi.mock('../services/clinicalCases', () => ({getDefaultCases: async () => []}));
vi.mock('../services/personalities', () => ({getPersonalities: async () => []}));
vi.mock('../services/users/manageUsers', () => ({listManagedUsers: async () => ({users: [], total: 0})}));
vi.mock('../utils/apiFetch', () => ({apiFetch: reads.request}));

beforeEach(() => {
  vi.resetAllMocks();
  reads.own.mockResolvedValue([{id: 12}]);
  reads.organization.mockResolvedValue({interviews: [{id: 22}], total: 1});
  reads.detail.mockResolvedValue({id: 12, userId: 1, status: 'completed', reviewAccess: {canViewAssessments: true}});
  reads.recap.mockResolvedValue({});
  reads.request.mockResolvedValue({ok: true});
});
afterEach(cleanup);

it('preloads authorized conversation and evaluation JSON without requesting playback media', async () => {
  const user = {id: 1, role: 'student', preferredLanguage: 'es'} as User;
  render(<SessionListsProvider user={user} interviewFlow={false}><span>Ready</span></SessionListsProvider>);
  await waitFor(() => expect(reads.request).toHaveBeenCalledTimes(3));
  expect(reads.detail).toHaveBeenCalledWith('12', 'es');
  expect(reads.recap).toHaveBeenCalledWith(12);
  expect(reads.organization).not.toHaveBeenCalled();
  expect(reads.request.mock.calls.some(([url]) => /assets|speech|poster/.test(url))).toBe(false);
});

it('does not start background review preloads during an active interview', async () => {
  const user = {id: 1, role: 'student'} as User;
  render(<SessionListsProvider user={user} interviewFlow><span>Ready</span></SessionListsProvider>);
  await waitFor(() => expect(reads.own).toHaveBeenCalled());
  expect(reads.detail).not.toHaveBeenCalled();
});

it('uses the organization history for a superuser without loading another account own history', async () => {
  reads.detail.mockResolvedValue({id: 22, userId: 2, status: 'completed', reviewAccess: {canViewAssessments: true, canAssignTeachers: true}});
  const user = {id: 1, role: 'superuser', organizationId: 42} as User;
  render(<SessionListsProvider user={user} interviewFlow={false}><span>Ready</span></SessionListsProvider>);
  await waitFor(() => expect(reads.request).toHaveBeenCalledTimes(3));
  expect(reads.organization).toHaveBeenCalledWith('42', 0, 100);
  expect(reads.detail).toHaveBeenCalledWith('22', 'en');
  expect(reads.own).not.toHaveBeenCalled();
});
