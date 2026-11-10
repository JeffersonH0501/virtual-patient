import {Badge} from '../Badge';
import {FC, useEffect, useRef, useState} from 'react';
import {useOnOutsideClick, useUser} from '../../../hooks';
import {useTranslation} from 'react-i18next';
import {LanguageSwitcher} from '../LanguageSwitcher';
import {Button} from '../Button';
import {useAppMotion, useMotionVisibility} from '../Motion/hooks';

type Props = {
  open: boolean;
  onOutsideClick?: (event?: MouseEvent) => void;
  onSignOut: () => void;
  triggerElement?: HTMLElement | null;
};

export const Menu: FC<Props> = ({open, onOutsideClick, onSignOut, triggerElement = null}) => {
  const {enabled} = useAppMotion();
  const visible = useMotionVisibility();
  open = open && visible;
  const [elementReference, setElementReference] = useState<HTMLDivElement | null>(null);
  const {user} = useUser();
  const {t} = useTranslation();
  const returnFocus = useRef(false);
  useOnOutsideClick(onOutsideClick, [elementReference, triggerElement], !open);
  useEffect(
    () => () => {
      if (returnFocus.current || elementReference?.contains(document.activeElement)) {
        triggerElement?.focus();
      }
    },
    [elementReference, triggerElement],
  );

  useEffect(() => {
    if (!open || !elementReference) return;
    returnFocus.current = false;
    elementReference.querySelector<HTMLElement>('select, button')?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (
        event.key === 'Escape' &&
        !elementReference.querySelector('[role="combobox"][aria-expanded="true"]')
      ) {
        returnFocus.current = true;
        onOutsideClick?.();
      }
    };
    elementReference.addEventListener('keydown', handleKey);
    return () => elementReference.removeEventListener('keydown', handleKey);
  }, [open, elementReference, triggerElement]);

  const roleLabel =
    user?.role === 'teacher'
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
      className="profile-menu motion-popup absolute right-0 z-50 mt-layout w-72 overflow-hidden rounded-panel border border-border bg-surface text-left shadow-modal"
      data-ui-motion={enabled ? 'app' : undefined}
      data-motion-state={open ? 'open' : 'closed'}
      aria-hidden={!open || undefined}
      inert={!open}
      ref={setElementReference}
      id="profile-menu"
      role="group"
      aria-label={t('navigation.profile')}
    >
      {user && (
        <div className="flex flex-col items-start gap-layout ui-divider-bottom border-border p-inset">
          <Badge tone="success">{roleLabel}</Badge>
          <div className="ui-text-pair w-full">
            <p className="truncate text-neutral-800 default-text">{user.name}</p>
            <p className="truncate text-neutral-500 secondary-text" title={user.email}>
              {user.email}
            </p>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-layout ui-divider-bottom border-border px-inset py-inset">
        <span className="text-neutral-700 medium-text">{t('common.language')}</span>
        <LanguageSwitcher />
      </div>

      <div className="ui-button-group--large flex justify-center p-inset">
        <Button variant="danger" onClick={handleSignOut}>
          {t('auth.signOut')}
        </Button>
      </div>
    </div>
  );
};
