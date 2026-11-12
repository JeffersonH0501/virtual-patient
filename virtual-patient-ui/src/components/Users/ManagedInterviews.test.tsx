import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {MemoryRouter} from 'react-router-dom';
import {ManagedInterviews} from './ManagedInterviews';

vi.mock('react-i18next', async (importOriginal) => ({
  ...await importOriginal<typeof import('react-i18next')>(),
  useTranslation: () => ({t: (key: string) => key}),
}));
vi.mock('../../services/users/manageUsers', () => ({getManagedInterviews: vi.fn(async () => [{
  id: 8, publicId: 'interview-8', createdAt: '2026-01-01T00:00:00Z', startTime: '2026-01-01T00:00:00Z',
  status: 'completed', totalDuration: 30, clinicalCase: {title: 'Test case'}, evaluationScore: null,
  isAssigned: true, manualRatingStatus: 'pending',
}])}));
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: {id: 1, role: 'admin', organizationId: 1}})}));
vi.mock('../../hooks/useSessionList', () => ({useSessionList: () => ({items: [{
  id: 8, userId: 3, userName: 'Student', ownerRole: 'student', createdAt: '2026-01-01T00:00:00Z',
  startTime: '2026-01-01T00:00:00Z', status: 'completed', clinicalCaseTitle: 'Test case',
}], loading: false, load: vi.fn()})}));
afterEach(cleanup);

it('shows assigned interviews with their assessment status in the standard admin table', async () => {
  render(<MemoryRouter><ManagedInterviews userId={5} /></MemoryRouter>);
  expect(await screen.findByText('conversations.assigned')).toBeDefined();
  expect(screen.getByText('conversations.pendingEvaluation')).toBeDefined();
  expect(screen.getByRole('button', {name: 'conversations.deleteInterview'})).toBeDefined();
});
