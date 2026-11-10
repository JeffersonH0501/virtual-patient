import {afterEach, expect, it, vi} from 'vitest';
import {createRef, useState} from 'react';
import {Modal} from '../Modal';
import {CustomSelect} from '../CustomSelect';
import {FormInput} from '../FormInput';
import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {Select} from './index';

vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
afterEach(cleanup);
const options = [
  {value: 'auto', label: 'Automatic', searchText: 'Automatic'},
  {value: 'teacher', label: <><strong>Teacher:</strong>{' '}Ada</>, searchText: 'Teacher: Ada'},
  {value: 'manage', label: <strong>Assign Teacher</strong>, searchText: 'Assign Teacher'},
];
it('emphasizes only the teacher prefix in the popup and selected value', () => {
  const changed = vi.fn();
  const view = render(<Select label="Source" value="auto" options={options} onValueChange={changed} />);
  const control = screen.getByRole('combobox', {name: 'Source'});
  fireEvent.click(control);
  const teacher = screen.getByRole('option', {name: 'Teacher: Ada'});
  expect(teacher.querySelector('strong')?.textContent).toBe('Teacher:');
  fireEvent.click(teacher);
  expect(changed).toHaveBeenCalledWith('teacher');
  expect(screen.queryByRole('listbox')).toBeNull();
  view.rerender(<Select label="Source" value="teacher" options={options} onValueChange={changed} />);
  expect(within(control).getByText('Teacher:').tagName).toBe('STRONG');
  expect(control.textContent).toBe('Teacher: Ada');
});
it('supports arrows, Home, End, selection and Escape without changing the value on navigation', () => {
  const changed = vi.fn();
  render(<Select label="Source" value="auto" options={options} onValueChange={changed} />);
  const control = screen.getByRole('combobox');
  control.focus();
  fireEvent.keyDown(control, {key: 'Enter'});
  fireEvent.keyDown(control, {key: 'End'});
  expect(control.getAttribute('aria-activedescendant')).toBe(screen.getByRole('option', {name: 'Assign Teacher'}).id);
  fireEvent.keyDown(control, {key: 'Home'});
  fireEvent.keyDown(control, {key: 'ArrowDown'});
  fireEvent.keyDown(control, {key: 'Enter'});
  expect(changed).toHaveBeenCalledWith('teacher');
  expect(document.activeElement).toBe(control);
  changed.mockClear();
  fireEvent.keyDown(control, {key: 'ArrowUp'});
  fireEvent.keyDown(control, {key: 'Escape'});
  expect(screen.queryByRole('listbox')).toBeNull();
  expect(changed).not.toHaveBeenCalled();
});
it('supports typeahead and closes on outside interaction or Tab', () => {
  const changed = vi.fn();
  render(<><Select label="Source" value="auto" options={options} onValueChange={changed} /><button>Outside</button></>);
  const control = screen.getByRole('combobox');
  fireEvent.keyDown(control, {key: 't'});
  expect(control.getAttribute('aria-activedescendant')).toBe(screen.getByRole('option', {name: 'Teacher: Ada'}).id);
  fireEvent.pointerDown(screen.getByRole('button', {name: 'Outside'}));
  expect(screen.queryByRole('listbox')).toBeNull();
  fireEvent.click(control);
  fireEvent.keyDown(control, {key: 'Tab'});
  expect(screen.queryByRole('listbox')).toBeNull();
  expect(changed).not.toHaveBeenCalled();
});
it('retains required validation, form values, disabled fields and legacy change events', () => {
  const changed = vi.fn();
  const ref = createRef<HTMLButtonElement>();
  const Form = ({disabled = false}: {disabled?: boolean}) => {
    const [value, setValue] = useState('');
    return <form><Select
      ref={ref}
      name="language"
      label="Language"
      value={value}
      required
      disabled={disabled}
      options={[{value: '', label: 'Choose', disabled: true}, {value: 'en', label: 'English'}, {value: 'es', label: 'Spanish', disabled: true}]}
      onChange={(event) => {
        changed(event.target.value);
        setValue(event.target.value);
      }}
    /></form>;
  };
  const view = render(<Form />);
  const control = screen.getByRole('combobox');
  const form = view.container.querySelector('form')!;
  let valid = true;
  act(() => {
    valid = form.checkValidity();
  });
  expect(valid).toBe(false);
  expect(control.getAttribute('aria-invalid')).toBe('true');
  expect(document.activeElement).toBe(control);
  fireEvent.click(control);
  expect(screen.getByRole('option', {name: 'Choose'}).getAttribute('aria-disabled')).toBe('true');
  fireEvent.keyDown(control, {key: 'End'});
  expect(control.getAttribute('aria-activedescendant')).toBe(screen.getByRole('option', {name: 'English'}).id);
  fireEvent.keyDown(control, {key: 'Enter'});
  expect(changed).toHaveBeenCalledWith('en');
  expect(form.checkValidity()).toBe(true);
  expect(new FormData(form).get('language')).toBe('en');
  expect(ref.current).toBe(control);
  fireEvent.click(control);
  view.rerender(<Form disabled />);
  expect((control as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByRole('listbox')).toBeNull();
  expect(new FormData(form).has('language')).toBe(false);
});
it('keeps popup interaction and the first Escape inside a dismissible dialog', async () => {
  const close = vi.fn();
  const changed = vi.fn();
  render(<Modal open closeAction={close} ariaLabel="Form"><Select label="Source" value="auto" options={options} onValueChange={changed} /></Modal>);
  const control = await screen.findByRole('combobox');
  fireEvent.click(control);
  const list = screen.getByRole('listbox');
  expect(list.closest('[data-ui-select-portal-host]')).not.toBeNull();
  const teacher = screen.getByRole('option', {name: 'Teacher: Ada'});
  fireEvent.mouseUp(teacher);
  expect(close).not.toHaveBeenCalled();
  fireEvent.click(teacher);
  expect(changed).toHaveBeenCalledWith('teacher');
  fireEvent.click(control);
  fireEvent.keyDown(control, {key: 'Escape', keyCode: 27});
  expect(screen.queryByRole('listbox')).toBeNull();
  expect(close).not.toHaveBeenCalled();
  fireEvent.keyDown(control, {key: 'Escape', keyCode: 27});
  expect(close).toHaveBeenCalledTimes(1);
});
it('keeps the string-value field wrapper controlled and its loading state disabled', () => {
  const changed = vi.fn();
  const Field = ({disabled = false}: {disabled?: boolean}) => {
    const [value, setValue] = useState('');
    return <CustomSelect id="personality" label="Personality" placeholder="Choose a personality" value={value} disabled={disabled} options={['Friendly', 'Reserved']} onChange={(next) => {
      changed(next);
      setValue(next);
    }} />;
  };
  const view = render(<Field />);
  const control = screen.getByLabelText('Personality');
  expect(control.textContent).toBe('Choose a personality');
  fireEvent.click(control);
  expect(screen.queryByRole('option', {name: 'Choose a personality'})).toBeNull();
  fireEvent.click(screen.getByRole('option', {name: 'Friendly'}));
  expect(changed).toHaveBeenCalledWith('Friendly');
  expect(control.textContent).toBe('Friendly');
  view.rerender(<Field disabled />);
  expect((control as HTMLButtonElement).disabled).toBe(true);
});
it('preserves FormInput native change callbacks, labels, errors and focus refs', () => {
  const changed = vi.fn();
  const ref = createRef<HTMLButtonElement>();
  const Field = () => {
    const [value, setValue] = useState('First');
    return <FormInput ref={ref} id="choice" name="choice" type="select" label="Choice" placeholder="Choose" options={['First', 'Second']} value={value} error="Review this choice" onChange={(event) => {
      changed(event.target.tagName, event.target.value);
      setValue(event.target.value);
    }} />;
  };
  render(<Field />);
  const control = screen.getByLabelText('Choice');
  expect(control.getAttribute('aria-invalid')).toBe('true');
  expect(control.getAttribute('aria-describedby')).toContain('choice-error');
  expect(screen.getByRole('alert').textContent).toBe('Review this choice');
  fireEvent.click(control);
  fireEvent.click(screen.getByRole('option', {name: 'Second'}));
  expect(changed).toHaveBeenCalledWith('SELECT', 'Second');
  expect(control.textContent).toBe('Second');
  expect(ref.current).toBe(control);
});

