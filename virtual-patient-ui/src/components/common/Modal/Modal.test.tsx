import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {useState} from 'react';
import {Modal} from './index';
import {Field} from '../Field';
vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
afterEach(cleanup);
const Example = () => {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      <Modal open={open} hasActions closeAction={() => setOpen(false)}>
        <h2>Editor</h2>
        <Field id="name" label="Name" hint="Help" error="Invalid name" />
        <button onClick={() => setOpen(false)}>Cancel</button>
      </Modal>
    </>
  );
};
it('labels the dialog, contains keyboard focus and restores the trigger', async () => {
  render(<Example />);
  const trigger = screen.getByText('Open');
  trigger.focus();
  fireEvent.click(trigger);
  const input = await screen.findByLabelText('Name');
  await waitFor(() => expect(document.activeElement).toBe(input));
  expect(screen.getByRole('dialog').getAttribute('aria-labelledby')).toBe(
    screen.getByText('Editor').id,
  );
  expect(input.getAttribute('aria-invalid')).toBe('true');
  expect(input.getAttribute('aria-describedby')).toBe('name-hint name-error');
  fireEvent.keyDown(input, {key: 'Tab', shiftKey: true});
  expect(document.activeElement).toBe(screen.getByText('Cancel'));
  fireEvent.keyDown(screen.getByText('Cancel'), {key: 'Tab'});
  expect(document.activeElement).toBe(input);
  fireEvent.click(screen.getByText('Cancel'));
  await waitFor(() => expect(document.activeElement).toBe(trigger));
});
