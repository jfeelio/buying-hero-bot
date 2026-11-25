import React from 'react';
import {staticFile, continueRender, delayRender, Easing, interpolate} from 'remotion';

export const BLUE = '#0083CA';
export const GREEN = '#2ECC71';
export const RED = '#EB4D4B';
export const GOLD = '#FFD23C';
export const PANEL = 'rgba(10,12,16,0.88)';

// Montserrat (OFL) from public/ - loaded once before the first frame renders
let loaded = false;
export const useFonts = () => {
  if (loaded) return;
  loaded = true;
  const h = delayRender('fonts');
  const faces = [
    new FontFace('MontBlack', `url(${staticFile('Montserrat-Black.ttf')})`),
    new FontFace('MontXB', `url(${staticFile('Montserrat-ExtraBold.ttf')})`),
    new FontFace('Anton', `url(${staticFile('Anton.ttf')})`),
  ];
  Promise.all(faces.map((f) => f.load())).then((fs) => {
    fs.forEach((f) => (document as any).fonts.add(f));
    continueRender(h);
  });
};

export const money = (v: number) => '$' + Math.round(v).toLocaleString('en-US');

export const easeOut = (frame: number, start: number, len: number) =>
  interpolate(frame, [start, start + len], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic),
  });

/** running total at `frame`: each step's amount rolls in over `roll` frames (ease-out) after its cue */
export const totalAt = (steps: {f: number; value?: number}[], frame: number, roll = 21) =>
  steps.reduce((acc, s) => acc + (s.value ?? 0) * easeOut(frame, s.f, roll), 0);

export const fadeInOut = (frame: number, dur: number, len = 7) =>
  Math.min(easeOut(frame, 0, len), 1 - easeOut(frame, dur - len, len));
