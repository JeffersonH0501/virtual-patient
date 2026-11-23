import {afterEach, expect, it, vi} from 'vitest';
import {getInterview} from './getInterview';
import {apiFetch} from '../../utils/apiFetch';

vi.mock('../../utils/apiFetch', () => ({apiFetch: vi.fn()}));
vi.mock('../auth/authHeaders', () => ({getAuthHeaders: () => ({})}));
afterEach(() => vi.resetAllMocks());

it.each([404, 500])('preserves HTTP %s so the session can distinguish deletion from a temporary failure', async (status) => {
  vi.mocked(apiFetch).mockResolvedValue(new Response(JSON.stringify({detail: 'Synthetic interview error'}), {status}));
  await expect(getInterview('11189')).rejects.toMatchObject({status, message: 'Synthetic interview error'});
});
