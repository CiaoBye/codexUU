import { useEffect, useRef, useState } from 'react';

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(media.matches);
    update();
    media.addEventListener?.('change', update);
    return () => media.removeEventListener?.('change', update);
  }, []);

  return reduced;
}

export function useAnimatedNumber(target: number, duration = 440): number {
  const reduced = useReducedMotion();
  const [value, setValue] = useState(target);
  const current = useRef(target);

  useEffect(() => {
    if (reduced || !Number.isFinite(target)) {
      current.current = target;
      setValue(target);
      return;
    }
    if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') {
      current.current = target;
      setValue(target);
      return;
    }

    const start = current.current;
    const delta = target - start;
    if (Math.abs(delta) < 0.5) {
      current.current = target;
      setValue(target);
      return;
    }

    let frame = 0;
    const startedAt = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = start + delta * eased;
      current.current = next;
      setValue(next);
      if (progress < 1) frame = window.requestAnimationFrame(tick);
      else current.current = target;
    };

    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame?.(frame);
  }, [duration, reduced, target]);

  return value;
}
