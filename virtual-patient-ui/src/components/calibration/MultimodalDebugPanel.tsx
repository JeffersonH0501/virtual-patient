import {PointerEvent as ReactPointerEvent, useCallback, useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {
  DebugUnavailable,
  OpenSmileFrameDebug,
  PyFeatFrameDebug,
  isDebugUnavailable,
} from '../../services/debug';

// DEV/DEBUG-ONLY floating panel that renders the latest RAW frame-level
// multimodal observations. It shows only raw extractor values (no processed
// features, base/integrated labels, or aggregates). It is draggable,
// collapsible, fixed-position, and does not affect page layout.

export type MultimodalDebugPanelProps = {
  pyfeat: PyFeatFrameDebug | DebugUnavailable | null;
  opensmile: OpenSmileFrameDebug | DebugUnavailable | null;
  frameProcessingMs: number | null;
  sampleFps: number | null;
  onClose?: () => void;
};

type Position = {x: number; y: number};

const PANEL_WIDTH = 320;
const INITIAL_MARGIN = 16;

const clamp = (value: number, min: number, max: number): number =>
  Math.min(Math.max(value, min), max);

// Formats a nullable number with fixed precision, returning null when missing so
// the caller can render the "not available" placeholder instead of a fake zero.
const fmt = (value: number | null | undefined, digits: number, suffix = ''): string | null => {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  return `${value.toFixed(digits)}${suffix}`;
};

const Row = ({
  label,
  value,
  reason,
}: {
  label: string;
  value: string | null;
  reason?: string;
}) => {
  const na = value === null;
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5">
      <span className="text-neutral-400">{label}</span>
      <span
        className={`font-mono tabular-nums ${na ? 'text-neutral-500' : 'text-neutral-100'}`}
        title={reason || undefined}
      >
        {value}
      </span>
    </div>
  );
};

export const MultimodalDebugPanel = ({
  pyfeat,
  opensmile,
  frameProcessingMs,
  sampleFps,
  onClose,
}: MultimodalDebugPanelProps) => {
  const {t} = useTranslation();
  const na = t('calibration.debug.na');
  const yes = t('calibration.debug.yes');
  const no = t('calibration.debug.no');

  const [collapsed, setCollapsed] = useState(false);
  const [position, setPosition] = useState<Position>(() => ({
    x: Math.max(INITIAL_MARGIN, window.innerWidth - PANEL_WIDTH - INITIAL_MARGIN),
    y: INITIAL_MARGIN + 56,
  }));
  const dragOffset = useRef<Position | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const onPointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const rect = panelRef.current?.getBoundingClientRect();
    if (!rect) return;
    dragOffset.current = {x: event.clientX - rect.left, y: event.clientY - rect.top};
    (event.target as HTMLElement).setPointerCapture(event.pointerId);
  }, []);

  const onPointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const offset = dragOffset.current;
    if (!offset) return;
    const width = panelRef.current?.offsetWidth ?? PANEL_WIDTH;
    const height = panelRef.current?.offsetHeight ?? 0;
    const nextX = clamp(event.clientX - offset.x, 0, window.innerWidth - width);
    const nextY = clamp(event.clientY - offset.y, 0, window.innerHeight - Math.min(height, window.innerHeight));
    setPosition({x: nextX, y: nextY});
  }, []);

  const onPointerUp = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    dragOffset.current = null;
    (event.target as HTMLElement).releasePointerCapture?.(event.pointerId);
  }, []);

  // Re-clamp into view if the window shrinks.
  useEffect(() => {
    const onResize = () => {
      setPosition((current) => ({
        x: clamp(current.x, 0, Math.max(0, window.innerWidth - PANEL_WIDTH)),
        y: clamp(current.y, 0, Math.max(0, window.innerHeight - 48)),
      }));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const pyfeatUnavailable = pyfeat !== null && isDebugUnavailable(pyfeat);
  const opensmileUnavailable = opensmile !== null && isDebugUnavailable(opensmile);
  const pf = pyfeat && !isDebugUnavailable(pyfeat) ? pyfeat : null;
  const os = opensmile && !isDebugUnavailable(opensmile) ? opensmile : null;

  const reasonText = (key: string): string | undefined => {
    const raw = pf?.reasons?.[key] ?? os?.reasons?.[key];
    if (!raw) return undefined;
    // Prefer a localized short string when one exists for this reason code.
    const localized = t(`calibration.debug.reason.${raw}`, {defaultValue: raw});
    return localized;
  };

  const boolLabel = (value: boolean): string => (value ? yes : no);

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-label={t('calibration.debug.title')}
      className="fixed z-[1000] flex max-h-[70vh] flex-col overflow-hidden rounded-lg border border-neutral-700 bg-neutral-900/95 text-xs text-neutral-200 shadow-2xl backdrop-blur"
      style={{left: position.x, top: position.y, width: PANEL_WIDTH}}
    >
      <div
        className="flex cursor-move select-none items-center justify-between gap-2 border-b border-neutral-700 bg-neutral-800 px-3 py-2"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        <span className="font-semibold tracking-wide text-neutral-100">
          {t('calibration.debug.title')}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="rounded px-1.5 py-0.5 text-neutral-300 hover:bg-neutral-700"
            aria-expanded={!collapsed}
            aria-label={t('calibration.debug.title')}
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? '▸' : '▾'}
          </button>
          {onClose && (
            <button
              type="button"
              className="rounded px-1.5 py-0.5 text-neutral-300 hover:bg-neutral-700"
              aria-label={t('calibration.debug.off')}
              onClick={onClose}
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {!collapsed && (
        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
          {/* OpenFace 3.0 (visual extractor) */}
          <section className="mb-3">
            <h3 className="mb-1 text-[0.7rem] font-semibold uppercase tracking-wider text-sky-400">
              {t('calibration.debug.sections.openface')}
            </h3>
            {pyfeatUnavailable ? (
              <p className="text-neutral-500">
                {reasonText('extractor')
                  || t(`calibration.debug.reason.${(pyfeat as DebugUnavailable).reason}`, {
                    defaultValue: (pyfeat as DebugUnavailable).reason,
                  })}
              </p>
            ) : (
              <>
                <Row
                  label={t('calibration.debug.fields.faceDetected')}
                  value={pf ? boolLabel(pf.faceDetected) : na}
                  reason={reasonText('face')}
                />
                <Row
                  label={t('calibration.debug.fields.faceConfidence')}
                  value={pf ? (fmt(pf.faceScore, 3) ?? na) : na}
                  reason={reasonText('faceScore')}
                />
                <Row
                  label={t('calibration.debug.fields.gazeYaw')}
                  value={pf ? (fmt(pf.gazeYaw, 3) ?? na) : na}
                  reason={reasonText('gaze')}
                />
                <Row
                  label={t('calibration.debug.fields.gazePitch')}
                  value={pf ? (fmt(pf.gazePitch, 3) ?? na) : na}
                  reason={reasonText('gaze')}
                />
                <Row
                  label={t('calibration.debug.fields.headYaw')}
                  value={pf ? (fmt(pf.headYaw, 2, '°') ?? na) : na}
                  reason={reasonText('headPose')}
                />
                <Row
                  label={t('calibration.debug.fields.headPitch')}
                  value={pf ? (fmt(pf.headPitch, 2, '°') ?? na) : na}
                  reason={reasonText('headPose')}
                />
                <Row
                  label={t('calibration.debug.fields.headRoll')}
                  value={pf ? (fmt(pf.headRoll, 2, '°') ?? na) : na}
                  reason={reasonText('headPose')}
                />
                <Row
                  label={t('calibration.debug.fields.au12')}
                  value={pf ? (fmt(pf.au12, 2) ?? na) : na}
                  reason={reasonText('au12')}
                />
                <Row
                  label={t('calibration.debug.fields.frameTimestamp')}
                  value={pf ? (fmt(pf.frameTimestampMs, 0, ' ms') ?? na) : na}
                />
                <Row
                  label={t('calibration.debug.fields.processingFps')}
                  value={
                    sampleFps !== null || frameProcessingMs !== null
                      ? `${fmt(sampleFps, 1) ?? na} / ${fmt(frameProcessingMs, 0, ' ms') ?? na}`
                      : na
                  }
                />
              </>
            )}
          </section>

          {/* OPENSMILE */}
          <section>
            <h3 className="mb-1 text-[0.7rem] font-semibold uppercase tracking-wider text-emerald-400">
              {t('calibration.debug.sections.opensmile')}
            </h3>
            {opensmileUnavailable ? (
              <p className="text-neutral-500">
                {t(`calibration.debug.reason.${(opensmile as DebugUnavailable).reason}`, {
                  defaultValue: (opensmile as DebugUnavailable).reason,
                })}
              </p>
            ) : (
              <>
                <Row
                  label={t('calibration.debug.fields.f0')}
                  value={os ? (fmt(os.f0Semitones, 2, ' st') ?? na) : na}
                  reason={reasonText('f0')}
                />
                <Row
                  label={t('calibration.debug.fields.loudness')}
                  value={os ? (fmt(os.loudness, 3) ?? na) : na}
                  reason={reasonText('loudness')}
                />
                <Row
                  label={t('calibration.debug.fields.voicing')}
                  value={
                    os
                      ? fmt(os.voicing, 3) !== null
                        ? `${fmt(os.voicing, 3)}${os.voicingKind ? ` (${os.voicingKind})` : ''}`
                        : na
                      : na
                  }
                  reason={reasonText('voicing')}
                />
                <Row
                  label={t('calibration.debug.fields.frameTimestamp')}
                  value={os ? (fmt(os.frameTimestampMs, 0, ' ms') ?? na) : na}
                />
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
};
