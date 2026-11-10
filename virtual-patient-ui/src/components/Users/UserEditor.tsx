import {Dialog} from '../common/Dialog';
import {FormEvent, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {User} from '../../types/user';
import {
  createManagedUser,
  ManagedUserPayload,
  ManagedUserUpdate,
  updateManagedUser,
} from '../../services/users/manageUsers';
import {Button, Field, Select} from '../common';

type UserEditorProps = {account?: User; onClose: () => void; onSaved: (created: boolean) => void};

export const UserEditor = ({account, onClose, onSaved}: UserEditorProps) => {
  const {t} = useTranslation();
  const [form, setForm] = useState<Omit<ManagedUserPayload, 'role'> & {role: ManagedUserPayload['role'] | ''}>({
    name: account?.name ?? '',
    email: account?.email ?? '',
    role: account?.role === 'teacher' ? 'teacher' : account ? 'student' : '',
    password: '',
  });
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [error, setError] = useState('');
  const name = form.name.trim();
  const email = form.email.trim().toLowerCase();
  const nameChanged = Boolean(account && name !== account.name.trim());
  const emailChanged = Boolean(account && email !== account.email.trim().toLowerCase());
  const roleChanged = Boolean(account && form.role !== account.role);
  const hasChanges =
    !account || nameChanged || emailChanged || roleChanged || form.password.length > 0;
  const passwordValid = Boolean(form.password.trim()) || Boolean(account && form.password === '');
  const valid = Boolean(form.role && name && /^[^\s@]+@[^\s@]+$/.test(email) && passwordValid);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const {role} = form;
    if (!role || !valid || !hasChanges || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError('');
    try {
      const payload = {name, email, role};
      if (account) {
        const changes: ManagedUserUpdate = {};
        if (nameChanged) changes.name = name;
        if (emailChanged) changes.email = email;
        if (roleChanged) changes.role = role;
        if (form.password) changes.password = form.password;
        await updateManagedUser(account.id, changes);
      } else await createManagedUser({...payload, password: form.password});
      setForm((current) => ({...current, password: ''}));
      onSaved(!account);
    } catch (failure: unknown) {
      setError(failure instanceof Error ? failure.message : 'errors.generic');
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };
  return (
    <Dialog
      title={t(account ? 'users.edit' : 'users.new')}
      onClose={onClose}
      busy={busy}
      onSubmit={submit}
      hasDismissAction
      actions={
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={!valid || !hasChanges || busy}>
            {t(busy ? 'users.saving' : account ? 'users.save' : 'users.createAction')}
          </Button>
        </>
      }
    >
      <Field
        id="user-name"
        name="name"
        label={t('auth.name')}
        value={form.name}
        required
        disabled={busy}
        onChange={(event) => setForm({...form, name: event.target.value})}
      />
      <Field
        id="user-email"
        name="email"
        label={t('auth.email')}
        type="email"
        autoCapitalize="none"
        spellCheck={false}
        value={form.email}
        required
        disabled={busy}
        onChange={(event) => setForm({...form, email: event.target.value})}
      />
      <div className="ui-field">
        <label htmlFor="user-role">{t('auth.role')}</label>
        <Select
          id="user-role"
          label={t('auth.role')}
          placeholder={t('users.selectRole')}
          value={form.role}
          disabled={busy}
          onValueChange={(value) => setForm({...form, role: value as ManagedUserPayload['role']})}
          options={[
            {value: 'student', label: t('auth.student')},
            {value: 'teacher', label: t('auth.teacher')},
          ]}
        />
      </div>
      <Field
        id="user-password"
        name="password"
        label={t('auth.password')}
        type="password"
        autoComplete="new-password"
        value={form.password}
        required={!account}
        disabled={busy}
        hint={account ? t('users.passwordHint') : undefined}
        onChange={(event) => setForm({...form, password: event.target.value})}
      />
      {error && (
        <p className="ui-notice ui-notice--danger" role="alert">
          {t(error, {defaultValue: t('errors.generic')})}
        </p>
      )}
    </Dialog>
  );
};
