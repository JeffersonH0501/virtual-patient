import {useContext, useEffect, useMemo, useSyncExternalStore} from 'react';
import {createLists, SessionListsContext, type Lists} from '../contexts/sessionListsStore';

export function useSessionList<Key extends keyof Lists>(key: Key, enabled = true) {
  const shared = useContext(SessionListsContext);
  const local = useMemo(() => createLists(), []);
  const list = (shared ?? local)[key] as {
    load: Lists[Key]['load'];
    subscribe: Lists[Key]['subscribe'];
    read: () => ReturnType<Lists[Key]['read']>;
  };
  const snapshot = useSyncExternalStore(list.subscribe, list.read);
  useEffect(() => {
    if (enabled) void list.load();
  }, [enabled, list]);
  return {...snapshot, load: list.load};
}

