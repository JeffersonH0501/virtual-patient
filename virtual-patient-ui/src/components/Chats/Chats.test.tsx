import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {Chats} from './index';
const actor = vi.hoisted(() => ({role: 'teacher'}));
vi.mock('../../hooks', () => ({useUser: () => ({user: actor})}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
vi.mock('./ConversationTable', () => ({ConversationTable: () => <div>Interview history</div>}));
vi.mock('../Students', () => ({Students: () => <div>Administrative history</div>}));
afterEach(cleanup);
it.each(['student', 'teacher'])('shows one interview table without view selectors for %s', (role) => {
  actor.role = role;
  render(<MemoryRouter><Chats /></MemoryRouter>);
  expect(screen.getByText('Interview history')).toBeTruthy();
  expect(screen.queryByRole('group')).toBeNull();
});
it('preserves the administrative list', () => {
  actor.role = 'superuser';
  render(<MemoryRouter><Chats /></MemoryRouter>);
  expect(screen.getByText('Administrative history')).toBeTruthy();
});
