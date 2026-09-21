import { useSyncExternalStore, type CSSProperties } from 'react';

export type CoraState = 'idle' | 'correct' | 'celebrate';

export interface CoraMascotProps {
  state?: CoraState;
  /** Directory containing the four cora SVG files. */
  basePath?: string;
  /** Increment to restart the same one-shot reaction. */
  replayKey?: number | string;
  size?: number | string;
  /** Empty by default: the mascot is decorative next to the application's text. */
  alt?: string;
  className?: string;
  style?: CSSProperties;
}

const motionQuery = '(prefers-reduced-motion: reduce)';
const getReducedMotion = () => window.matchMedia(motionQuery).matches;
const getServerReducedMotion = () => true;
const subscribeToMotion = (callback: () => void) => {
  const query = window.matchMedia(motionQuery);
  query.addEventListener('change', callback);
  return () => query.removeEventListener('change', callback);
};

/**
 * Offline asset adapter. Copy the cora SVGs into your bundled public directory.
 * The source files contain their own animations; no animation library is needed.
 * Use the standalone laboratory when you need expression and pause controls.
 */
export function CoraMascot({
  state = 'idle',
  basePath = '/mascots/cora',
  replayKey = 0,
  size = 240,
  alt = '',
  className,
  style,
}: CoraMascotProps) {
  const reducedMotion = useSyncExternalStore(
    subscribeToMotion,
    getReducedMotion,
    getServerReducedMotion,
  );
  const filename = reducedMotion ? 'cora.svg' : `cora-${state}.svg`;
  const directory = basePath.replace(/\/$/, '');
  const source = `${directory}/${filename}?reaction=${encodeURIComponent(String(replayKey))}`;
  return (
    <img
      key={`${filename}:${replayKey}`}
      src={source}
      alt={alt}
      aria-hidden={alt === '' ? true : undefined}
      className={className}
      draggable={false}
      style={{ display: 'block', width: size, maxWidth: '100%', height: 'auto', ...style }}
    />
  );
}

export default CoraMascot;
