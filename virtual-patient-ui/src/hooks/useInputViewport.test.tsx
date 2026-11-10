import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {useInputViewport} from './useInputViewport';

let viewport: EventTarget & {height: number; offsetTop: number; scale: number};
let frames: Map<number, FrameRequestCallback>;
let nextFrame: number;
const flush = () => act(() => {
  const pending = [...frames.values()];
  frames.clear();
  pending.forEach((callback) => callback(0));
});
const bounds = (top: number, bottom: number) => ({top, bottom, height: bottom - top, left: 0, right: 200, width: 200} as DOMRect);
const field = (top: number, bottom: number, type = 'text') => {
  const input = document.createElement('input');
  input.type = type;
  input.scrollIntoView = vi.fn();
  vi.spyOn(input, 'getBoundingClientRect').mockReturnValue(bounds(top, bottom));
  document.body.append(input);
  input.focus();
  return input;
};
beforeEach(() => {
  viewport = Object.assign(new EventTarget(), {height: 800, offsetTop: 0, scale: 1});
  frames = new Map();
  nextFrame = 0;
  vi.stubGlobal('visualViewport', viewport);
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback: FrameRequestCallback) => {
    frames.set(++nextFrame, callback);
    return nextFrame;
  }));
  vi.stubGlobal('cancelAnimationFrame', vi.fn((id: number) => frames.delete(id)));
});
afterEach(() => {
  cleanup();
  document.body.replaceChildren();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it('adapts to keyboard opening and closing without changing text, selection or focus', () => {
  const input = field(600, 640);
  input.value = 'Unsaved draft';
  input.setSelectionRange(3, 3);
  renderHook(useInputViewport);
  flush();
  expect(input.scrollIntoView).not.toHaveBeenCalled();
  viewport.height = 350;
  act(() => viewport.dispatchEvent(new Event('resize')));
  flush();
  expect(document.documentElement.style.getPropertyValue('--app-viewport-height')).toBe('350px');
  expect(input.scrollIntoView).toHaveBeenCalledExactlyOnceWith({block: 'nearest', inline: 'nearest', behavior: 'instant'});
  expect(input.value).toBe('Unsaved draft');
  expect(input.selectionStart).toBe(3);
  expect(document.activeElement).toBe(input);
  viewport.height = 800;
  act(() => viewport.dispatchEvent(new Event('resize')));
  flush();
  expect(document.documentElement.style.getPropertyValue('--app-viewport-height')).toBe('800px');
  expect(input.scrollIntoView).toHaveBeenCalledTimes(1);
});

it('reveals a textarea clipped by a dialog body even inside the visible screen', () => {
  const scroller = document.createElement('div');
  scroller.style.overflowY = 'auto';
  vi.spyOn(scroller, 'getBoundingClientRect').mockReturnValue(bounds(100, 400));
  const textarea = document.createElement('textarea');
  textarea.scrollIntoView = vi.fn();
  vi.spyOn(textarea, 'getBoundingClientRect').mockReturnValue(bounds(420, 500));
  scroller.append(textarea);
  document.body.append(scroller);
  textarea.focus();
  renderHook(useInputViewport);
  flush();
  expect(textarea.scrollIntoView).toHaveBeenCalledOnce();
});

it('follows visual viewport offsets without fighting manual viewport panning', () => {
  const input = field(10, 50);
  renderHook(useInputViewport);
  flush();
  viewport.offsetTop = 80;
  act(() => viewport.dispatchEvent(new Event('scroll')));
  flush();
  expect(document.documentElement.style.getPropertyValue('--app-viewport-top')).toBe('80px');
  expect(input.scrollIntoView).not.toHaveBeenCalled();
});

it('preserves native pinch zoom without shrinking or scrolling the layout', () => {
  const input = field(600, 640);
  renderHook(useInputViewport);
  flush();
  viewport.scale = 2;
  viewport.height = 250;
  act(() => viewport.dispatchEvent(new Event('resize')));
  flush();
  expect(document.documentElement.style.getPropertyValue('--app-viewport-height')).toBe('800px');
  expect(input.scrollIntoView).not.toHaveBeenCalled();
});

it.each(['checkbox', 'range', 'button'])('does not scroll non-text input %s', (type) => {
  const input = field(900, 940, type);
  renderHook(useInputViewport);
  flush();
  expect(input.scrollIntoView).not.toHaveBeenCalled();
});

it('supports browsers without VisualViewport', () => {
  vi.stubGlobal('visualViewport', undefined);
  vi.stubGlobal('innerHeight', 350);
  const input = field(600, 640, 'number');
  renderHook(useInputViewport);
  flush();
  expect(document.documentElement.style.getPropertyValue('--app-viewport-height')).toBe('350px');
  expect(input.scrollIntoView).toHaveBeenCalledOnce();
});

it('leaves read-only fields and already visible text untouched while typing', () => {
  const input = field(100, 140);
  renderHook(useInputViewport);
  flush();
  act(() => input.dispatchEvent(new Event('input', {bubbles: true})));
  flush();
  expect(input.scrollIntoView).not.toHaveBeenCalled();
  input.readOnly = true;
  viewport.height = 80;
  act(() => viewport.dispatchEvent(new Event('resize')));
  flush();
  expect(input.scrollIntoView).not.toHaveBeenCalled();
});

it('coalesces viewport and focus events and cleans listeners and pending frames on unmount', () => {
  const input = field(600, 640);
  const {unmount} = renderHook(useInputViewport);
  act(() => {
    viewport.height = 350;
    viewport.dispatchEvent(new Event('resize'));
    window.dispatchEvent(new Event('resize'));
    input.dispatchEvent(new Event('input', {bubbles: true}));
  });
  expect(frames.size).toBe(1);
  flush();
  expect(input.scrollIntoView).toHaveBeenCalledOnce();
  act(() => viewport.dispatchEvent(new Event('resize')));
  unmount();
  expect(frames.size).toBe(0);
  expect(document.documentElement.style.getPropertyValue('--app-viewport-height')).toBe('');
  act(() => {
    viewport.dispatchEvent(new Event('resize'));
    input.dispatchEvent(new Event('input', {bubbles: true}));
  });
  expect(frames.size).toBe(0);
});
