import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {StrictMode, useEffect, useState} from 'react';
import {
  MotionContent,
  MotionHeight,
  MotionPresence,
  MotionProvider,
  MotionDetails,
  MotionRow,
} from './index';
import {Modal} from '../Modal';

vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));

beforeEach(() => {
  document.documentElement.style.setProperty('--app-motion-fast', '180ms');
  document.documentElement.style.setProperty('--app-motion-enter', '320ms');
  document.documentElement.style.setProperty('--app-motion-expand', '420ms');
  document.documentElement.style.setProperty('--app-motion-exit', '260ms');
  document.documentElement.style.setProperty('--app-motion-distance', '12px');
  document.documentElement.style.setProperty('--app-motion-stagger', '35ms');
  document.documentElement.style.setProperty('--app-motion-stagger-limit', '140ms');
  document.documentElement.style.setProperty('--motion-panel-easing', 'linear');
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it('retains a closing dialog without interaction, cancels removal on reopening and restores focus after exit', async () => {
  vi.useFakeTimers();
  const mounted = vi.fn();
  const Editor = ({onClose}: {onClose: () => void}) => {
    useEffect(() => {
      mounted();
    }, []);
    return (
      <Modal open hasActions closeAction={onClose}>
        <h2>Editor</h2>
        <button onClick={onClose}>Close</button>
      </Modal>
    );
  };
  const Example = () => {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button onClick={() => setOpen(true)}>Open</button>
        <MotionPresence visible={open}>
          {open && <Editor onClose={() => setOpen(false)} />}
        </MotionPresence>
      </>
    );
  };
  render(
    <MotionProvider>
      <Example />
    </MotionProvider>,
  );
  const trigger = screen.getByText('Open');
  trigger.focus();
  fireEvent.click(trigger);
  expect(screen.getByRole('dialog')).toBeTruthy();
  fireEvent.click(screen.getByText('Close'));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.getByRole('dialog', {hidden: true}).closest('[inert]')).not.toBeNull();
  act(() => vi.advanceTimersByTime(60));
  trigger.focus();
  fireEvent.click(trigger);
  expect(document.activeElement).toBe(screen.getByText('Close'));
  act(() => vi.advanceTimersByTime(120));
  expect(screen.getByRole('dialog')).toBeTruthy();
  expect(mounted).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByText('Close'));
  await act(async () => vi.advanceTimersByTime(261));
  expect(screen.queryByRole('dialog', {hidden: true})).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

it('skips presence delays with reduced motion and leaves unscoped consumers static', () => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn()})),
  );
  const {rerender} = render(
    <MotionProvider>
      <MotionPresence visible>
        <span>Popup</span>
      </MotionPresence>
    </MotionProvider>,
  );
  rerender(
    <MotionProvider>
      <MotionPresence visible={false}>
        <span>Popup</span>
      </MotionPresence>
    </MotionProvider>,
  );
  expect(screen.queryByText('Popup')).toBeNull();
  const animate = vi.fn();
  Object.defineProperty(HTMLElement.prototype, 'animate', {configurable: true, value: animate});
  rerender(<MotionContent changeKey="auth">Authentication content</MotionContent>);
  expect(animate).not.toHaveBeenCalled();
});

it('fades route content without remounting its live subtree and cancels obsolete animations', () => {
  const cancel = vi.fn();
  const animate = vi.fn(() => ({cancel}));
  Object.defineProperty(HTMLElement.prototype, 'animate', {configurable: true, value: animate});
  const mounted = vi.fn();
  const Media = () => {
    useEffect(() => {
      mounted();
    }, []);
    return <video data-testid="media" />;
  };
  const {rerender} = render(
    <MotionProvider>
      <MotionContent changeKey="first">
        <Media />
      </MotionContent>
    </MotionProvider>,
  );
  const media = screen.getByTestId('media');
  rerender(
    <MotionProvider>
      <MotionContent changeKey="second">
        <Media />
      </MotionContent>
    </MotionProvider>,
  );
  expect(screen.getByTestId('media')).toBe(media);
  expect(mounted).toHaveBeenCalledTimes(1);
  expect(animate).toHaveBeenCalledTimes(2);
  expect(cancel).toHaveBeenCalledTimes(1);
});

it.each([true, false])('measures asynchronous growth without transforming content, with fade=%s', (fade) => {
  const animate = vi.fn(() => ({cancel: vi.fn(), onfinish: null}));
  Object.defineProperty(HTMLElement.prototype, 'animate', {configurable: true, value: animate});
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    return {
      height:
        this.classList.contains('motion-height-content') && this.textContent === 'Loaded'
          ? 200
          : 40,
    } as DOMRect;
  });
  let resized = () => undefined;
  const disconnect = vi.fn();
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback: () => void) {
        resized = callback;
      }
      observe = vi.fn();
      disconnect = disconnect;
    },
  );
  const {rerender, unmount} = render(
    <MotionProvider>
      <MotionHeight fade={fade}>Loading</MotionHeight>
    </MotionProvider>,
  );
  rerender(
    <MotionProvider>
      <MotionHeight fade={fade}>Loaded</MotionHeight>
    </MotionProvider>,
  );
  act(() => resized());
  const frames = animate.mock.calls.at(-1)?.[0] as unknown as Record<string, string>[];
  expect(frames.at(-1)?.height).toBe('200px');
  expect(frames.some((frame) => 'transform' in frame)).toBe(false);
  expect(frames.some((frame) => 'opacity' in frame)).toBe(fade);
  unmount();
  expect(disconnect).toHaveBeenCalled();
});

it('retains native disclosures for the entire close and cancels a close on rapid reopening', () => {
  vi.useFakeTimers();
  render(
    <MotionProvider>
      <MotionDetails summary="Rubric">
        <button>Criterion</button>
      </MotionDetails>
    </MotionProvider>,
  );
  const summary = screen.getByText('Rubric').closest('summary')!;
  const details = summary.closest('details')!;
  expect(details.open).toBe(false);
  expect(screen.queryByRole('button', {name: 'Criterion'})).toBeNull();
  fireEvent.click(summary);
  expect(details.open).toBe(true);
  expect(screen.getByRole('button', {name: 'Criterion'})).toBeTruthy();
  fireEvent.click(summary);
  expect(summary.getAttribute('aria-expanded')).toBe('false');
  expect(screen.queryByRole('button', {name: 'Criterion'})).toBeNull();
  act(() => vi.advanceTimersByTime(419));
  expect(details.open).toBe(true);
  fireEvent.click(summary);
  act(() => vi.advanceTimersByTime(500));
  expect(details.open).toBe(true);
  expect(screen.getAllByRole('button', {name: 'Criterion'})).toHaveLength(1);
  fireEvent.click(summary);
  act(() => vi.advanceTimersByTime(420));
  expect(details.open).toBe(false);
});

it('staggers newly mounted rows with a bounded delay and never repeats for polling or reordering', () => {
  const animate = vi.fn((frames: Keyframe[], options: KeyframeAnimationOptions) => ({
    cancel: vi.fn(),
    frames,
    options,
  }));
  Object.defineProperty(HTMLElement.prototype, 'animate', {configurable: true, value: animate});
  const Rows = ({updated = false}: {updated?: boolean}) => (
    <MotionProvider>
      <table>
        <tbody>
          {(updated ? [9, 1, 0] : [0, 1, 9]).map((index) => (
            <MotionRow key={index} entranceIndex={index}>
              <td>
                {updated ? 'Updated ' : 'Row '}
                {index}
              </td>
            </MotionRow>
          ))}
        </tbody>
      </table>
    </MotionProvider>
  );
  const {rerender} = render(<Rows />);
  expect(animate.mock.calls.map(([, options]) => options.delay)).toEqual([0, 35, 140]);
  expect(
    animate.mock.calls.every(([frames]) => frames.every((frame) => !('transform' in frame))),
  ).toBe(true);
  const first = screen.getByText('Row 0').closest('tr');
  rerender(<Rows updated />);
  expect(animate).toHaveBeenCalledTimes(3);
  expect(screen.getByText('Updated 0').closest('tr')).toBe(first);
});

it('makes form entrances visible without remounting inputs or delaying interaction', () => {
  const animate = vi.fn((frames: Keyframe[], options: KeyframeAnimationOptions) => ({
    cancel: vi.fn(),
    frames,
    options,
  }));
  Object.defineProperty(HTMLElement.prototype, 'animate', {configurable: true, value: animate});
  const content = (key: string) => (
    <MotionProvider>
      <MotionContent changeKey={key} slide>
        <input aria-label="Email" />
      </MotionContent>
    </MotionProvider>
  );
  const {rerender} = render(content('signin'));
  const input = screen.getByLabelText('Email') as HTMLInputElement;
  fireEvent.change(input, {target: {value: 'example@example.org'}});
  expect(animate.mock.calls[0][0][0].transform).toBe('translateY(12px)');
  expect(animate.mock.calls[0][1].duration).toBe(320);
  rerender(content('changed'));
  expect(screen.getByLabelText('Email')).toBe(input);
  expect(input.value).toBe('example@example.org');
});

it('opens and closes disclosures immediately with reduced motion', () => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn()})),
  );
  const animate = vi.fn();
  Object.defineProperty(HTMLElement.prototype, 'animate', {configurable: true, value: animate});
  render(
    <MotionProvider>
      <MotionDetails summary="Rubric">Content</MotionDetails>
    </MotionProvider>,
  );
  const summary = screen.getByText('Rubric').closest('summary')!;
  fireEvent.click(summary);
  fireEvent.click(summary);
  expect(summary.closest('details')?.open).toBe(false);
  expect(animate).not.toHaveBeenCalled();
});

it('keeps an active entrance after the development Strict Mode effect replay', () => {
  const animate = vi.fn(() => ({cancel: vi.fn()}));
  Object.defineProperty(HTMLElement.prototype, 'animate', {configurable: true, value: animate});
  render(
    <StrictMode>
      <MotionProvider>
        <table>
          <tbody>
            <MotionRow>
              <td>Row</td>
            </MotionRow>
          </tbody>
        </table>
      </MotionProvider>
    </StrictMode>,
  );
  expect(animate).toHaveBeenCalledTimes(2);
  expect(animate.mock.results[0].value.cancel).toHaveBeenCalledTimes(1);
  expect(animate.mock.results[1].value.cancel).not.toHaveBeenCalled();
});
