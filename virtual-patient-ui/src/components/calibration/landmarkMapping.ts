// Pure geometry helpers for mapping raw Py-Feat landmark pixel coordinates onto
// the calibration preview video. Kept in a dedicated module (no component
// exports) so they are trivially unit-testable and do not break React fast
// refresh.

// Describes how the video content is laid out inside its element with
// object-contain: the content is scaled to fit while preserving aspect ratio
// and centered, leaving letterbox/pillarbox margins.
export type ContentBox = {
  contentLeft: number;
  contentTop: number;
  contentWidth: number;
  contentHeight: number;
};

// Computes the displayed content box for an object-contain element given the
// element's client size and the source image's intrinsic size. Returns a zero
// box for degenerate inputs.
export const computeContainContentBox = (
  elementWidth: number,
  elementHeight: number,
  imageWidth: number,
  imageHeight: number,
): ContentBox => {
  if (
    elementWidth <= 0 || elementHeight <= 0
    || imageWidth <= 0 || imageHeight <= 0
  ) {
    return {contentLeft: 0, contentTop: 0, contentWidth: 0, contentHeight: 0};
  }
  const scale = Math.min(elementWidth / imageWidth, elementHeight / imageHeight);
  const contentWidth = imageWidth * scale;
  const contentHeight = imageHeight * scale;
  return {
    contentLeft: (elementWidth - contentWidth) / 2,
    contentTop: (elementHeight - contentHeight) / 2,
    contentWidth,
    contentHeight,
  };
};

// Maps a single landmark from image-pixel space to element/display CSS pixels,
// accounting for object-contain letterboxing and the CSS horizontal mirror.
//
//   displayX = mirrored
//     ? contentLeft + (1 - x / imageWidth) * contentWidth
//     : contentLeft + (x / imageWidth) * contentWidth
//   displayY = contentTop + (y / imageHeight) * contentHeight
export const mapLandmarkToDisplay = (
  x: number,
  y: number,
  imageWidth: number,
  imageHeight: number,
  box: ContentBox,
  mirrored: boolean,
): {x: number; y: number} => {
  const normX = x / imageWidth;
  const normY = y / imageHeight;
  const displayX = mirrored
    ? box.contentLeft + (1 - normX) * box.contentWidth
    : box.contentLeft + normX * box.contentWidth;
  const displayY = box.contentTop + normY * box.contentHeight;
  return {x: displayX, y: displayY};
};
