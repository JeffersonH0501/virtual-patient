import {describe, expect, it} from 'vitest';

import {computeContainContentBox, mapLandmarkToDisplay} from './landmarkMapping';

// Pure-unit tests for the calibration landmark geometry helpers. These are the
// most valuable tests for the debug tool: the mirror + letterbox math is what
// makes the overlaid landmarks line up with the mirrored preview video, and it
// is fully deterministic with no DOM.
//
// Runner note: this project has no test runner installed yet (no vitest/jest
// dependency), and `tsconfig.app.json` excludes `src/**/*.test.ts` from the
// production build. Following the existing precedent
// (`src/services/recap/normalizeObservation.test.ts`), these are authored in
// vitest style so they run unchanged once vitest (matching this Vite project)
// is added. They still type-check against the real exports.
//
// Hook coverage note: the `useMultimodalDebug` capture loop (ON/OFF toggle,
// single-inflight backpressure, and interval/stream cleanup) is intentionally
// NOT rendered here, because the project has no React testing library
// configured and this task must not add one. That behaviour is covered by the
// backend upload-guard tests plus manual verification; these frontend tests
// focus on the pure geometry that has no other coverage.

describe('computeContainContentBox', () => {
  it('pillarboxes a wide image inside a tall element (limited by width)', () => {
    // 200x100 image in a 100x200 element: width is the limiting dimension.
    // scale = min(100/200, 200/100) = min(0.5, 2) = 0.5.
    const box = computeContainContentBox(100, 200, 200, 100);

    expect(box.contentWidth).toBe(100); // 200 * 0.5
    expect(box.contentHeight).toBe(50); // 100 * 0.5
    expect(box.contentLeft).toBe(0); // (100 - 100) / 2
    expect(box.contentTop).toBe(75); // (200 - 50) / 2, centered vertically
  });

  it('letterboxes a tall image inside a wide element (limited by height)', () => {
    // 100x200 image in a 200x100 element: height is the limiting dimension.
    // scale = min(200/100, 100/200) = min(2, 0.5) = 0.5.
    const box = computeContainContentBox(200, 100, 100, 200);

    expect(box.contentWidth).toBe(50); // 100 * 0.5
    expect(box.contentHeight).toBe(100); // 200 * 0.5
    expect(box.contentLeft).toBe(75); // (200 - 50) / 2, centered horizontally
    expect(box.contentTop).toBe(0); // (100 - 100) / 2
  });

  it('returns a zero box for degenerate (non-positive) inputs', () => {
    expect(computeContainContentBox(0, 100, 200, 100)).toEqual({
      contentLeft: 0,
      contentTop: 0,
      contentWidth: 0,
      contentHeight: 0,
    });
    expect(computeContainContentBox(100, 100, 200, 0)).toEqual({
      contentLeft: 0,
      contentTop: 0,
      contentWidth: 0,
      contentHeight: 0,
    });
  });
});

describe('mapLandmarkToDisplay', () => {
  // A simple centered content box so the mirror math is easy to reason about:
  // content spans x in [10, 110] (width 100) and y in [20, 220] (height 200).
  const box = {contentLeft: 10, contentTop: 20, contentWidth: 100, contentHeight: 200};
  const imageWidth = 640;
  const imageHeight = 480;

  it('mirrors horizontally by default: image x=0 maps to the RIGHT edge', () => {
    // Default mirrored=true. normX = 0 -> displayX = left + (1 - 0) * width.
    const point = mapLandmarkToDisplay(0, 0, imageWidth, imageHeight, box, true);

    expect(point.x).toBe(110); // right edge (contentLeft + contentWidth)
    expect(point.y).toBe(20); // top -> contentTop
  });

  it('mirrors horizontally: image x=imageWidth maps to the LEFT edge', () => {
    // normX = 1 -> displayX = left + (1 - 1) * width = contentLeft.
    const point = mapLandmarkToDisplay(
      imageWidth,
      imageHeight,
      imageWidth,
      imageHeight,
      box,
      true,
    );

    expect(point.x).toBe(10); // left edge (contentLeft)
    expect(point.y).toBe(220); // bottom -> contentTop + contentHeight
  });

  it('un-mirrored maps image x=0 to the LEFT edge (no flip)', () => {
    const point = mapLandmarkToDisplay(0, 0, imageWidth, imageHeight, box, false);

    expect(point.x).toBe(10); // left edge, no horizontal flip
    expect(point.y).toBe(20);
  });

  it('maps a mid-frame point to the content-box center regardless of mirror', () => {
    // The exact center is invariant under horizontal mirroring.
    const center = imageWidth / 2;
    const mirrored = mapLandmarkToDisplay(center, imageHeight / 2, imageWidth, imageHeight, box, true);
    const straight = mapLandmarkToDisplay(center, imageHeight / 2, imageWidth, imageHeight, box, false);

    expect(mirrored.x).toBe(60); // contentLeft + 0.5 * contentWidth
    expect(mirrored.y).toBe(120); // contentTop + 0.5 * contentHeight
    expect(straight.x).toBe(60);
    expect(straight.y).toBe(120);
  });
});
