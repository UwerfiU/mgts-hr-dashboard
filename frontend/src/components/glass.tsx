import { createContext, lazy, Suspense, useContext, useEffect, useRef } from 'react';

export const GlassEnabled = createContext(false);

// The material is decorative. A failed GPU or chunk never hides chart content.
const GlassMaterial = lazy(() => import('./glass-material.tsx').catch(() => ({ default: () => null })));

export function GlassLayer() {
  const enabled = useContext(GlassEnabled);
  const layer = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = layer.current?.parentElement;
    if (!enabled || !host) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    function move(event: PointerEvent) {
      if (reduced.matches || event.pointerType === 'touch') return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const rect = host!.getBoundingClientRect();
        host!.style.setProperty('--shine-x', `${event.clientX - rect.left}px`);
        host!.style.setProperty('--shine-y', `${event.clientY - rect.top}px`);
      });
    }
    host.addEventListener('pointermove', move);
    return () => { cancelAnimationFrame(frame); host.removeEventListener('pointermove', move); };
  }, [enabled]);
  if (!enabled) return null;
  return (
    <div ref={layer} className="glass-layer" aria-hidden="true">
      <Suspense fallback={null}><GlassMaterial /></Suspense>
    </div>
  );
}
