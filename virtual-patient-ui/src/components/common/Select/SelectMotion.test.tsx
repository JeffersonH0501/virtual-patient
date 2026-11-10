import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {MotionProvider} from '../Motion';
import {Select} from './index';

vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
beforeEach(() => {
  vi.useFakeTimers();
  document.documentElement.style.setProperty('--app-motion-expand', '420ms');
  document.documentElement.style.setProperty('--layout-inset', '15px');
  document.documentElement.style.setProperty('--select-menu-max-height', '280px');
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  for (const key of ['--app-motion-expand', '--layout-inset', '--select-menu-max-height']) {
    document.documentElement.style.removeProperty(key);
  }
});
const options = [
  {value: 'one', label: 'One'},
  {value: 'two', label: 'Two'},
];

it.each(['top', 'bottom'] as const)(
  'anchors %s, commits selection immediately and retains an inert menu for the full exit',
  (placement) => {
    const changed = vi.fn();
    render(
      <MotionProvider>
        <Select label="Source" value="one" options={options} onValueChange={changed} />
      </MotionProvider>,
    );
    const trigger = screen.getByRole('combobox');
    const top = placement === 'top' ? window.innerHeight - 60 : 60;
    vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({
      left: 20,
      right: 220,
      width: 200,
      top,
      bottom: top + 40,
      height: 40,
    } as DOMRect);
    fireEvent.click(trigger);
    expect(screen.getByRole('listbox').getAttribute('data-placement')).toBe(placement);
    fireEvent.click(screen.getByRole('option', {name: 'Two'}));
    expect(changed).toHaveBeenCalledWith('two');
    expect(document.activeElement).toBe(trigger);
    expect(screen.queryByRole('listbox')).toBeNull();
    const closing = screen.getByRole('listbox', {hidden: true});
    expect(closing.hasAttribute('inert')).toBe(true);
    act(() => vi.advanceTimersByTime(419));
    expect(screen.getByRole('listbox', {hidden: true})).toBe(closing);
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole('listbox', {hidden: true})).toBeNull();
  },
);

it('cancels removal on reopening and closes with Escape or an outside click', () => {
  render(
    <MotionProvider>
      <Select label="Source" value="one" options={options} />
    </MotionProvider>,
  );
  const trigger = screen.getByRole('combobox');
  fireEvent.click(trigger);
  fireEvent.keyDown(trigger, {key: 'Escape'});
  act(() => vi.advanceTimersByTime(200));
  fireEvent.click(trigger);
  act(() => vi.advanceTimersByTime(500));
  expect(screen.getAllByRole('listbox')).toHaveLength(1);
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole('listbox')).toBeNull();
  act(() => vi.advanceTimersByTime(420));
  expect(screen.queryByRole('listbox', {hidden: true})).toBeNull();
});

it('removes menus immediately for reduced motion', () => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn()})),
  );
  render(
    <MotionProvider>
      <Select label="Source" value="one" options={options} />
    </MotionProvider>,
  );
  const trigger = screen.getByRole('combobox');
  fireEvent.click(trigger);
  fireEvent.keyDown(trigger, {key: 'Escape'});
  expect(screen.queryByRole('listbox', {hidden: true})).toBeNull();
});
