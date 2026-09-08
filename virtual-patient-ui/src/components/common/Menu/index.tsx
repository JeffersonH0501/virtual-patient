import {FC, useState} from 'react';
import {useOnOutsideClick, useUser} from '../../../hooks';
import {useTranslation} from 'react-i18next';
import {LanguageSwitcher} from '../LanguageSwitcher';

type Props = {
  open: boolean;
  onOutsideClick?: (event?: MouseEvent) => void;
  onSignOut: () => void;
  triggerElement?: HTMLElement | null;
};

export const Menu: FC<Props> = ({open, onOutsideClick, onSignOut, triggerElement = null}) => {
  const [elementReference, setElementReference] = useState<HTMLDivElement | null>(null);
  const {user} = useUser();
  const {t} = useTranslation();
  useOnOutsideClick(onOutsideClick, [elementReference, triggerElement], !open);

  const roleLabel = user?.role === 'teacher'
    ? t('common.teacher')
    : user?.role === 'superuser'
      ? t('common.superuser')
      : t('common.student');

  const handleSignOut = () => {
    onOutsideClick?.();
    onSignOut();
  };

  return (
    <div
      className="profile-menu absolute right-0 z-50 mt-1 w-72 overflow-hidden rounded-panel border border-border bg-surface text-left shadow-modal"
      ref={setElementReference}
      role="menu"
    >
      {user && (
        <div className="border-b border-border px-4 py-4">
          <span className="inline-flex rounded-full bg-brand-100 px-2.5 py-1 text-xs font-semibold text-brand-700">
            {roleLabel}
          </span>
          <p className="mt-3 truncate text-sm font-semibold text-slate-800">
            {[user.firstName, user.lastName].filter(Boolean).join(' ')}
          </p>
          <p className="mt-1 truncate text-xs text-slate-500" title={user.email}>
            {user.email}
          </p>
        </div>
      )}

      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <span className="text-sm font-medium text-slate-700">{t('common.language')}</span>
        <LanguageSwitcher />
      </div>

      <button
        type="button"
        role="menuitem"
        onClick={handleSignOut}
        className="block w-full px-4 py-3 text-left text-sm font-medium text-slate-700 transition-colors hover:bg-danger-50 hover:text-danger-700 focus-visible:bg-danger-50 focus-visible:text-danger-700 focus-visible:outline-none"
      >
        {t('auth.signOut')}
      </button>
    </div>
  );
};
