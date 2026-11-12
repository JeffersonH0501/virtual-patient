import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {Students} from './index';

vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string, params?: {name?: string}) => params?.name ? `${key} ${params.name}` : key})}));
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {role: 'admin'}})}));
vi.mock('../../hooks/useSessionList', () => ({useSessionList: () => ({items: [{id: 5, name: 'Jefferson Hernandez'}]})}));
vi.mock('./StudentsTable', () => ({StudentsTable: () => <p>all interviews</p>}));
vi.mock('../Users/ManagedInterviews', () => ({ManagedInterviews: () => <p>filtered interviews</p>}));
afterEach(cleanup);

it('clears the named filter and returns to the normal interview list', () => {
  const Location = () => <output>{useLocation().search || 'no filter'}</output>;
  render(<MemoryRouter initialEntries={['/interviews?user=5']}><Students /><Location /></MemoryRouter>);
  expect(screen.getByText('users.namedInterviews Jefferson Hernandez')).toBeDefined();
  expect(screen.getByText('filtered interviews')).toBeDefined();
  fireEvent.click(screen.getByRole('button', {name: 'users.clearInterviewFilter'}));
  expect(screen.getByText('all interviews')).toBeDefined();
  expect(screen.getByText('no filter')).toBeDefined();
  expect(screen.queryByRole('button', {name: 'users.clearInterviewFilter'})).toBeNull();
});
