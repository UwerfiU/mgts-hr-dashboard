import { useState } from 'react';
import { GlassContent, GlassScene, GlassSurface } from '@glass-sdk/liquid-glass';
import '@glass-sdk/liquid-glass/styles.css';

export default function GlassMaterial() {
  const [failed, setFailed] = useState(false);
  if (failed || !('gpu' in navigator) || !navigator.gpu ||
    window.matchMedia('(prefers-reduced-transparency: reduce), (forced-colors: active)').matches) return null;
  return (
    <GlassScene className="glass-scene" material="clear" appearance="light" motion="none" maxSurfaces={1}
      onDiagnostic={({ error }) => { if (error) setFailed(true); }}>
      {/* Only this opaque material is refracted. Text and chart SVGs stay above it. */}
      <GlassContent className="glass-source" />
      <GlassSurface className="glass-surface" radius={32} refraction={60} interactive={false} />
    </GlassScene>
  );
}
