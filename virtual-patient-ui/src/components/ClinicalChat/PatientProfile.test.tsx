import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {PatientProfile} from './PatientProfile';
import {Patient} from '../../types';
vi.mock('react-i18next', () => ({
  useTranslation: () => ({t: (key: string) => key, i18n: {resolvedLanguage: 'es'}}),
}));
afterEach(cleanup);
const patient: Patient = {
  id: '1',
  name: 'Synthetic patient',
  avatar: '',
  online: false,
  basicInfo: {age: 40, gender: 'female', bloodType: '', weight: ''},
  symptoms: [],
  allergies: [],
  diet: '',
  illnesses: [],
  medications: [],
  familyHistory: [],
  habits: [],
  workInformation: '',
  medicalHistory: [],
  summary: '',
};
it('shows the case details without interview timing rows', () => {
  const {container} = render(<PatientProfile patient={patient} caseTitle="Synthetic case" />);
  expect(screen.getByText('Synthetic case')).toBeDefined();
  expect(Array.from(container.querySelectorAll('dt'), (label) => label.textContent)).toEqual([
    'patientProfile.case:', 'patientProfile.name:', 'patientProfile.gender:',
    'patientProfile.age:', 'patientProfile.weight:', 'patientProfile.personality:',
  ]);
});

it('shows only inline interview details in review', () => {
  const {container} = render(<PatientProfile patient={{...patient, summary: 'Synthetic summary'}} isReview />);
  expect(Array.from(container.querySelectorAll('dt'), (label) => label.textContent)).toEqual([
    'patientProfile.case:',
    'patientProfile.personality:', 'patientProfile.gender:',
  ]);
  expect(container.querySelector('.patient-profile-details')).toBeNull();
});

it('shows the available clinical sections in preview before any data is collected', () => {
  render(<PatientProfile patient={patient} />);
  const symptoms = screen.getByText('patientProfile.currentSymptoms').closest('summary')!;
  expect(screen.getByText('patientProfile.medicalHistory').closest('summary')).not.toBeNull();
  expect(symptoms.getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(symptoms);
  expect(symptoms.getAttribute('aria-expanded')).toBe('true');
  expect(symptoms.parentElement?.textContent).toContain('patientProfile.emptySection');
});

it('moves populated sections first and keeps the open row expanded', () => {
  const {container, rerender} = render(<PatientProfile patient={patient} />);
  const diet = screen.getByText('patientProfile.diet').closest('summary')!;
  fireEvent.click(diet);
  rerender(<PatientProfile patient={{...patient, diet: 'Synthetic diet'}} />);
  expect(container.querySelector('details > summary')).toBe(diet);
  expect(diet.getAttribute('aria-expanded')).toBe('true');
  expect(diet.parentElement?.classList.contains('patient-profile-details--filled')).toBe(true);
});

it('keeps existing populated sections above newly populated sections', () => {
  const withSummary = {...patient, summary: 'Synthetic summary'};
  const {container, rerender} = render(<PatientProfile patient={withSummary} />);
  rerender(<PatientProfile patient={{...withSummary, diet: 'Synthetic diet'}} />);
  expect(Array.from(container.querySelectorAll('details > summary'), (row) => row.textContent).slice(0, 2))
    .toEqual(['patientProfile.summary', 'patientProfile.diet']);
});
