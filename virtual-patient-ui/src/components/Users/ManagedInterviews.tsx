import {StudentsTable} from '../Students/StudentsTable';
import {useCallback, useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {getManagedInterviews} from '../../services/users/manageUsers';
import {InterviewListItem} from '../../types/interview';

export function ManagedInterviews({userId}: {userId: number}) {
  const {t} = useTranslation();
  const [items, setItems] = useState<InterviewListItem[] | null>(null);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const load = useCallback(async (signal: {active: boolean}) => {
    try {
      const all: InterviewListItem[] = [];
      let batch: InterviewListItem[];
      do {
        batch = await getManagedInterviews(userId, all.length);
        all.push(...batch);
      } while (batch.length === 100 && signal.active);
      if (signal.active) {
        setItems(all); setError(false);
      }
    } catch {
      if (signal.active) setError(true);
    }
  }, [userId]);
  useEffect(() => {
    const signal = {active: true};
    setItems(null); setError(false);
    void load(signal);
    return () => {
      signal.active = false;
    };
  }, [load, retry]);
  useEffect(() => {
    if (!items?.some((item) => item.status === 'processing' || item.status === 'in_progress')) return;
    const signal = {active: true};
    const timer = window.setTimeout(() => void load(signal), 5000);
    return () => {
      signal.active = false; window.clearTimeout(timer);
    };
  }, [items, load]);
  if (error && !items) return <div role="alert">{t('errors.generic')} <button type="button" className="ui-action-text" onClick={() => setRetry((value) => value + 1)}>{t('common.retry')}</button></div>;
  if (!items) return <p role="status">{t('common.loading')}</p>;
  return <StudentsTable filteredItems={items} onFilteredChange={() => setRetry((value) => value + 1)} />;
}
