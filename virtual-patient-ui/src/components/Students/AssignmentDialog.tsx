import {Dialog} from '../common/Dialog';
import {useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Assignment, gradingRequest} from '../../services/doctorGrading';
import {User} from '../../types/user';
import {Button} from '../common';
import {Badge} from '../common/Badge';

export const AssignmentDialog = ({
  interviewId,
  ownerId,
  onClose,
  onSaved,
}: {
  interviewId: number;
  /** A doctor cannot review their own interview, so the owner is not offered. */
  ownerId?: number;
  onClose: () => void;
  onSaved?: () => void;
}) => {
  const {t} = useTranslation();
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [doctors, setDoctors] = useState<User[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const sending = useRef(false);
  const load = async (preserve = false) => {
    setBusy(true);
    try {
      const [items, people] = await Promise.all([
        gradingRequest<Assignment[]>('/medical-interviews/' + interviewId + '/doctor-assignments'),
        (async () => {
          const all: User[] = [];
          let offset = 0;
          while (true) {
            const page = await gradingRequest<{users: User[]; total: number}>(
              '/users/admin/doctors?offset=' + offset + '&limit=100',
            );
            all.push(...page.users.filter((person) => person.id !== ownerId));
            offset += page.users.length;
            if (offset >= page.total || !page.users.length) return all;
          }
        })(),
      ]);
      setAssignments(items);
      setDoctors(people);
      setSelected((current) =>
        preserve
          ? [
              ...new Set([
                ...current.filter(
                  (id) =>
                    people.some((person) => person.id === id) ||
                    items.some((item) => item.doctorId === id),
                ),
                ...items.filter((item) => item.status !== 'pending').map((item) => item.doctorId),
              ]),
            ]
          : items.map((item) => item.doctorId),
      );
      setLoaded(true);
    } catch {
      setError(t('errors.generic'));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    void load();
  }, [interviewId]);
  const save = async () => {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError('');
    try {
      await gradingRequest('/medical-interviews/' + interviewId + '/doctor-assignments', 'PUT', {
        doctor_ids: selected,
      });
      onSaved?.();
      onClose();
    } catch {
      setError(t('grading.assignmentFailed'));
      await load(true);
    } finally {
      sending.current = false;
      setBusy(false);
    }
  };
  const baseline = assignments.map((item) => item.doctorId);
  const changed =
    selected.length !== baseline.length || selected.some((id) => !baseline.includes(id));
  const people = [
    ...doctors.map((person) => ({id: person.id, name: person.name, email: person.email})),
    ...assignments
      .filter((item) => !doctors.some((person) => person.id === item.doctorId))
      .map((item) => ({
        id: item.doctorId,
        name: item.doctorName,
        email: item.doctorEmail ?? '',
      })),
  ];
  return (
    <Dialog
      title={t('grading.assignedDoctors')}
      onClose={onClose}
      busy={busy}
      size="medium"
      hasDismissAction
      actions={
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button disabled={busy || !loaded || !changed} onClick={() => void save()}>
            {t('common.save')}
          </Button>
        </>
      }
    >
      <p className="text-content-muted default-text">{t('grading.assignmentHint')}</p>
      {error && (
        <div>
          <p role="alert" className="ui-notice ui-notice--danger">
            {error}
          </p>
          {!loaded && (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => {
                setError('');
                void load();
              }}
            >
              {t('common.retry')}
            </Button>
          )}
        </div>
      )}
      {busy && !loaded ? (
        <div role="status" aria-label={t('common.loading')} aria-busy="true" className="grid gap-layout">
          <p role="status">{t('common.loading')}</p>
        </div>
      ) : (
        <div className="doctor-assignment-list" role="group" aria-label={t('grading.doctors')}>
          {people.map((person) => {
            const assignment = assignments.find((item) => item.doctorId === person.id);
            const locked = Boolean(assignment && assignment.status !== 'pending');
            return (
              <label className="doctor-assignment-row" key={person.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(person.id)}
                  disabled={busy || locked}
                  onChange={(event) =>
                    setSelected((current) =>
                      event.target.checked
                        ? [...current, person.id]
                        : current.filter((id) => id !== person.id),
                    )
                  }
                />
                <span className="ui-text-pair min-w-0">
                  <span className="block break-words medium-text">{person.name}</span>
                  <span className="block break-all text-content-muted secondary-text">
                    {person.email}
                  </span>
                </span>
                {assignment && (
                  <span className="doctor-assignment-status">
                    <Badge
                      tone={
                        assignment.status === 'submitted'
                          ? 'success'
                          : assignment.status === 'in_progress'
                            ? 'info'
                            : 'warning'
                      }
                    >
                      {t('grading.' + assignment.status)}
                    </Badge>
                  </span>
                )}
              </label>
            );
          })}
          {!people.length && loaded && <p className="ui-empty-state">{t('grading.noDoctors')}</p>}
        </div>
      )}
    </Dialog>
  );
};
