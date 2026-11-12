import {useTranslation} from 'react-i18next';
import {Select} from '../common/Select';
import {User} from '../../types/user';

export function SemesterSelect({id, value, onChange, required = false, disabled = false}: {
  id: string; value: NonNullable<User['semesterRange']> | ''; onChange: (value: NonNullable<User['semesterRange']>) => void;
  required?: boolean; disabled?: boolean;
}) {
  const {t} = useTranslation();
  return <div className="ui-field">
    <label htmlFor={id}>{t('auth.semester')}</label>
    <Select id={id} label={t('auth.semester')} placeholder={t('auth.selectSemester')} value={value}
      required={required} disabled={disabled} onValueChange={(next) => {
        if (next === 'first_four' || next === 'fifth_eighth' || next === 'ninth_plus') onChange(next);
      }} options={[
        {value: 'first_four', label: t('auth.semesterFirstFour')},
        {value: 'fifth_eighth', label: t('auth.semesterFifthEighth')},
        {value: 'ninth_plus', label: t('auth.semesterNinthPlus')},
      ]} />
  </div>;
}
