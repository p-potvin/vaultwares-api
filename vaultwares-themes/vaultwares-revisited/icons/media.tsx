import type { SVGProps } from 'react';

type P = SVGProps<SVGSVGElement>;
const d = { xmlns: 'http://www.w3.org/2000/svg', width: 24, height: 24, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

export function IconPlay(p: P) {
  return <svg {...d} {...p}><polygon points="5 3 19 12 5 21 5 3"/></svg>;
}

export function IconPause(p: P) {
  return <svg {...d} {...p}><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>;
}

export function IconStop(p: P) {
  return <svg {...d} {...p}><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/></svg>;
}

export function IconSkipForward(p: P) {
  return <svg {...d} {...p}><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/></svg>;
}

export function IconSkipBack(p: P) {
  return <svg {...d} {...p}><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/></svg>;
}

export function IconVolume(p: P) {
  return <svg {...d} {...p}><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>;
}

export function IconVolumeOff(p: P) {
  return <svg {...d} {...p}><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>;
}
