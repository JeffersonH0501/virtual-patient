import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {useState} from 'react';
import {Dialog} from './index';
import {Button} from '../Button';

vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
afterEach(cleanup);

it('restores focus after closing and can reopen without duplicating controls', async () => {
  const Example = () => {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button onClick={() => setOpen(true)}>Open</button>
        <Dialog open={open} title="Editor" onClose={() => setOpen(false)}>
          <input aria-label="Name" />
        </Dialog>
      </>
    );
  };
  render(<Example />);
  const trigger = screen.getByText('Open');
  trigger.focus();
  fireEvent.click(trigger);
  fireEvent.keyDown(document, {keyCode: 27});
  expect(screen.queryByRole('dialog')).toBeNull();
  await waitFor(() => expect(document.activeElement).toBe(trigger));
  fireEvent.click(trigger);
  expect(screen.getAllByRole('dialog')).toHaveLength(1);
  expect(screen.getAllByRole('button', {name: 'common.close'})).toHaveLength(1);
});

it('blocks every dismissal while busy and restores Escape when saving finishes', () => {
  const close = vi.fn();
  const {rerender} = render(
    <Dialog title="Editor" busy onClose={close}>
      <p>Saving</p>
    </Dialog>,
  );
  fireEvent.click(screen.getByRole('button', {name: 'common.close'}));
  fireEvent.keyDown(document, {keyCode: 27});
  expect(close).not.toHaveBeenCalled();
  rerender(
    <Dialog title="Editor" onClose={close}>
      <p>Ready</p>
    </Dialog>,
  );
  fireEvent.keyDown(document, {keyCode: 27});
  expect(close).toHaveBeenCalledTimes(1);
});

it('submits the form from its shared footer and keeps cancellation separate', () => {
  const submit = vi.fn((event) => event.preventDefault());
  const close = vi.fn();
  render(
    <Dialog
      title="Editor"
      onClose={close}
      onSubmit={submit}
      hasDismissAction
      actions={
        <>
          <Button variant="secondary" onClick={close}>
            Cancel
          </Button>
          <Button type="submit">Save</Button>
        </>
      }
    >
      <input aria-label="Name" defaultValue="Example" />
    </Dialog>,
  );
  fireEvent.click(screen.getByText('Save'));
  expect(screen.queryByRole('button', {name: 'common.close'})).toBeNull();
  expect(submit).toHaveBeenCalledTimes(1);
  expect(close).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('Cancel'));
  expect(close).toHaveBeenCalledTimes(1);
});

it('keeps the header close action when the footer only provides a save action', () => {
  const close = vi.fn();
  render(<Dialog title="Editor" onClose={close} actions={<Button>Save</Button>}><p>Content</p></Dialog>);
  fireEvent.click(screen.getByRole('button', {name: 'common.close'}));
  expect(close).toHaveBeenCalledOnce();
});
