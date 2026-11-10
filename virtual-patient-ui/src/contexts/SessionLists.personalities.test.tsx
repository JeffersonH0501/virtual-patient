import {cleanup, render, screen, waitFor} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {SessionListsProvider, useSessionList} from './SessionLists';
import type {User} from '../types/user';

const read = vi.hoisted(() => vi.fn());
vi.mock('../services/personalities', () => ({getPersonalities: read}));
vi.mock('../services/clinicalCases', () => ({getDefaultCases: async () => []}));
vi.mock('../services/interviews/getInterviews', () => ({getInterviews: async () => []}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const Consumer = () => {
  const {items, loading} = useSessionList('personalities');
  return <output>{loading ? 'pending' : items?.length}</output>;
};

it('preloads every page before opening configuration and retains personalities across view remounts', async () => {
  read.mockImplementation(async (offset: number) => offset === 0
    ? Array.from({length: 100}, (_, id) => ({id, name: `Personality ${id}`}))
    : [{id: 100, name: 'Last personality'}]);
  const user = {id: 1, role: 'student'} as User;
  const tree = (visible: boolean) => <SessionListsProvider user={user} interviewFlow={false}>
    {visible && <Consumer />}
  </SessionListsProvider>;
  const view = render(tree(false));
  await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
  view.rerender(tree(true));
  await screen.findByText('101');
  expect(read.mock.calls).toEqual([[0, 100], [100, 100]]);
  view.rerender(tree(false));
  view.rerender(tree(true));
  expect(screen.getByText('101')).toBeTruthy();
  expect(read).toHaveBeenCalledTimes(2);
});
