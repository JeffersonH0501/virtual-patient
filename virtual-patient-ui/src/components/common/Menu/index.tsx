import {FC, useState} from 'react';
import {useOnOutsideClick} from '../../../hooks';
import {useUser} from '../../../hooks';
import {useTranslation} from 'react-i18next';

type Props = {
  open: boolean;
  onOutsideClick?: (event: MouseEvent) => void;
  onSignOut: () => void;
};

export const Menu: FC<Props> = ({open, onOutsideClick, onSignOut}) => {
  const [elementReference, setElementReference] = useState<HTMLDivElement | null>();
  const {user} = useUser();
  const {t} = useTranslation();
  useOnOutsideClick(onOutsideClick, elementReference, !open);

  return (
    <div
      className="absolute right-0 mt-2 w-64 bg-white border border-gray-200 rounded-md shadow-lg"
      ref={setElementReference}
    >
      {/* User Info Section */}
      {user && (
        <div className="px-4 py-3 border-b border-gray-200 text-left">
          <p className="text-sm font-semibold text-gray-900 truncate">
            {user.fullName}
          </p>
          <p className="text-xs text-gray-600 truncate mt-0.5">
            @{user.username}
          </p>
          <p className="text-xs text-gray-500 truncate mt-1">
            {user.email}
          </p>
          <span className="inline-block mt-2 px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800">
            {user.role === 'teacher' ? t('common.teacher') : user.role === 'superuser' ? t('common.superuser') : t('common.student')}
          </span>
        </div>
      )}
      
      {/* Sign Out Button */}
      <button
        onClick={onSignOut}
        className="block w-full text-left px-4 py-2 text-gray-700 hover:bg-gray-100"
      >
        {t('auth.signOut')}
      </button>
    </div>
  );
};
