import {useEffect, useRef} from 'react';
import {computeContainContentBox, mapLandmarkToDisplay} from './landmarkMapping';

// DEV/DEBUG-ONLY overlay that draws raw Py-Feat facial landmarks over the
// calibration camera preview. It never intercepts pointer events and never
// alters the video; it only paints dots on a transparent, absolutely-positioned
// canvas that exactly tracks the video's displayed content area.

export type FacialLandmarksOverlayProps = {
  // Image-pixel [x, y] pairs relative to the raw (unmirrored) uploaded frame.
  landmarks: number[][] | null;
  imageWidth: number | null;
  imageHeight: number | null;
  videoEl: HTMLVideoElement | null;
  // The preview video is CSS-mirrored (-scale-x-100), so overlay coordinates
  // must be flipped horizontally to line up. Defaults to true.
  mirrored?: boolean;
};

const DOT_RADIUS_CSS = 1.6;
const DOT_COLOR = 'rgba(56, 189, 248, 0.9)';

export const FacialLandmarksOverlay = ({
  landmarks,
  imageWidth,
  imageHeight,
  videoEl,
  mirrored = true,
}: FacialLandmarksOverlayProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Keep latest values in refs so the ResizeObserver callback always redraws
  // with current data without re-subscribing.
  const landmarksRef = useRef(landmarks);
  landmarksRef.current = landmarks;
  const imageWidthRef = useRef(imageWidth);
  imageWidthRef.current = imageWidth;
  const imageHeightRef = useRef(imageHeight);
  imageHeightRef.current = imageHeight;
  const mirroredRef = useRef(mirrored);
  mirroredRef.current = mirrored;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !videoEl) return undefined;

    const draw = () => {
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const clientWidth = videoEl.clientWidth;
      const clientHeight = videoEl.clientHeight;
      const dpr = window.devicePixelRatio || 1;
      // Size the backing store by DPR for crisp dots; size the CSS box to the
      // video's displayed box.
      const backingWidth = Math.round(clientWidth * dpr);
      const backingHeight = Math.round(clientHeight * dpr);
      if (canvas.width !== backingWidth) canvas.width = backingWidth;
      if (canvas.height !== backingHeight) canvas.height = backingHeight;
      canvas.style.width = `${clientWidth}px`;
      canvas.style.height = `${clientHeight}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, clientWidth, clientHeight);

      const pts = landmarksRef.current;
      const imgW = imageWidthRef.current;
      const imgH = imageHeightRef.current;
      if (!pts || !imgW || !imgH) return;

      const box = computeContainContentBox(clientWidth, clientHeight, imgW, imgH);
      if (box.contentWidth <= 0) return;

      ctx.fillStyle = DOT_COLOR;
      const isMirrored = mirroredRef.current;
      for (const point of pts) {
        if (!point || point.length < 2) continue;
        const [x, y] = point;
        const mapped = mapLandmarkToDisplay(x, y, imgW, imgH, box, isMirrored);
        ctx.beginPath();
        ctx.arc(mapped.x, mapped.y, DOT_RADIUS_CSS, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    draw();
    const observer = new ResizeObserver(() => draw());
    observer.observe(videoEl);
    return () => observer.disconnect();
  }, [videoEl, landmarks, imageWidth, imageHeight, mirrored]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        pointerEvents: 'none',
      }}
    />
  );
};
