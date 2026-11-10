import {useState} from 'react';
import {useSessionList} from '../../contexts/SessionLists';
import {MANAGED_USERS_PAGE_SIZE as pageSize} from '../../services/users/manageUsers';

export const useManagedUsers = (enabled: boolean) => {
  const [requestedOffset, setOffset] = useState(0);
  const {items, loading, error, load} = useSessionList('users', enabled);
  const total = items?.length ?? 0;
  const offset = Math.min(requestedOffset, Math.floor(Math.max(0, total - 1) / pageSize) * pageSize);
  const reload = (reset = false) => {
    if (reset) setOffset(0);
    void load(true);
  };
  return {
    users: items?.slice(offset, offset + pageSize) ?? [],
    total,
    offset,
    loading: loading && items === undefined,
    error: error ?? '',
    reload,
    setOffset,
    pageSize,
  };
};
