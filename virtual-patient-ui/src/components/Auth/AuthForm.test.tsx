import {afterEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {AuthForm} from './AuthForm';
import {AuthLayout} from './AuthLayout';
import {WelcomeSection} from '../Login/WelcomeSection';

const mocks = vi.hoisted(() => ({create: vi.fn().mockResolvedValue({access_token: 'test'}), setUser: vi.fn()}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key, i18n: {language: 'es'}})}));
vi.mock('../../hooks/useUser', () => ({useUser: () => ({setUser: mocks.setUser})}));
vi.mock('../../services/users/createUser', () => ({createUser: mocks.create}));
vi.mock('../../services/users/getUser', () => ({getUser: async () => ({role: 'student'})}));
vi.mock('react-google-recaptcha', () => ({default: ({onChange}: {onChange: (token: string) => void}) =>
  <button type="button" onClick={() => onChange('test')}>Captcha</button>}));
afterEach(() => {
cleanup(); vi.clearAllMocks(); vi.unstubAllEnvs();
});

it.each([
  ['load', 'loaded'],
  ['error', 'unavailable'],
] as const)('loads the illustration without a skeleton after an image %s event', (event, status) => {
  const {container} = render(<WelcomeSection />);
  const frame = container.querySelector('.auth-illustration')!;
  const image = frame.querySelector('img')!;

  expect(frame.querySelector('.auth-illustration-placeholder')).toBeNull();
  fireEvent[event](image);

  expect(frame.querySelector('.auth-illustration-placeholder')).toBeNull();
  expect(frame.getAttribute('data-status')).toBe(status);
  expect(frame.querySelector('img')).toBe(image);
});

describe('public registration', () => {
  it.each(['student', 'teacher'])('requires a role and registers a %s with one password', async (role) => {
    vi.stubEnv('VITE_RECAPTCHA_SITE_KEY', 'test');
    render(<MemoryRouter><AuthForm mode="signup" onSwitchMode={() => {}} /></MemoryRouter>);
    expect(screen.queryByLabelText('auth.confirmPassword')).toBeNull();
    fireEvent.change(screen.getByLabelText('auth.name'), {target: {value: 'Student'}});
    fireEvent.change(screen.getByLabelText('auth.email'), {target: {value: 'student@example.org'}});
    fireEvent.change(screen.getByLabelText('auth.password'), {target: {value: 'test-password'}});
    fireEvent.click(screen.getByText('Captcha'));
    expect((screen.getByRole('button', {name: 'auth.signup'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('combobox', {name: 'auth.role'}));
    expect(screen.getAllByRole('option')).toHaveLength(2);
    fireEvent.click(screen.getByRole('option', {name: 'auth.' + role}));
    fireEvent.click(screen.getByRole('button', {name: 'auth.signup'}));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith({name: 'Student', email: 'student@example.org', password: 'test-password', role, captcha: 'test'}));
  });
  it('switches forms on the welcome route while keeping the illustration and CAPTCHA mounted', () => {
    vi.stubEnv('VITE_RECAPTCHA_SITE_KEY', 'test');
    const Location = () => <output aria-label="Current path">{useLocation().pathname}</output>;
    const {container} = render(
      <MemoryRouter initialEntries={['/welcome']}>
        <AuthLayout />
        <Location />
      </MemoryRouter>,
    );
    const illustration = container.querySelector('.auth-illustration img');
    const captcha = screen.getByRole('button', {name: 'Captcha'});
    expect(screen.queryByText('auth.forgotPassword')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'auth.signup'}));
    expect(screen.getByLabelText('auth.role')).toBeTruthy();
    expect(screen.getByLabelText('Current path').textContent).toBe('/welcome');
    expect(container.querySelector('.auth-illustration img')).toBe(illustration);
    expect(screen.getByRole('button', {name: 'Captcha'})).toBe(captcha);
    fireEvent.click(screen.getByRole('button', {name: 'auth.signIn'}));
    expect(screen.queryByLabelText('auth.role')).toBeNull();
  });
});
