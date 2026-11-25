import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {BLUE, GREEN, GOLD, PANEL, fadeInOut, useFonts} from './theme';

type Line = {text: string; color?: 'white' | 'blue' | 'green' | 'gold'; size?: number};
export type CardProps = {dur: number; y: number; lines: Line[]; panel?: boolean; stagger?: number};

export const cardDefaults: CardProps = {
  dur: 3, y: 330, panel: true, stagger: 0.18,
  lines: [{text: '$826,706 SO FAR', size: 70}, {text: '$173,294 TO GO', color: 'gold', size: 90}],
};
const COLORS = {white: 'white', blue: BLUE, green: GREEN, gold: GOLD};

/** Headline card: each line springs in, staggered. Centered on y. */
export const Card: React.FC<CardProps> = (p) => {
  useFonts();
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = fadeInOut(frame, Math.round(p.dur * fps), 6);
  const box = spring({frame, fps, config: {damping: 14, stiffness: 160}});
  return (
    <AbsoluteFill style={{opacity}}>
      <div style={{position: 'absolute', left: 0, right: 0, top: p.y, transform: 'translateY(-50%)',
                   display: 'flex', justifyContent: 'center'}}>
        <div style={{padding: p.panel ? '26px 44px' : 0, borderRadius: 30, maxWidth: 960,
                     background: p.panel ? PANEL : 'transparent', border: p.panel ? `5px solid ${BLUE}` : 'none',
                     boxShadow: p.panel ? '0 16px 44px rgba(0,0,0,0.55)' : 'none', textAlign: 'center',
                     transform: `scale(${0.85 + 0.15 * box})`}}>
          {p.lines.map((l, i) => {
            const s = spring({frame: frame - Math.round(i * (p.stagger ?? 0.18) * fps), fps,
                              config: {damping: 11, stiffness: 190}});
            return (
              <div key={i} style={{fontFamily: 'MontBlack', fontSize: l.size ?? 80, lineHeight: 1.12,
                                   color: COLORS[l.color ?? 'white'], opacity: Math.min(1, s * 1.4),
                                   transform: `translateY(${(1 - s) * 30}px) scale(${0.8 + 0.2 * s})`,
                                   textShadow: p.panel ? 'none' : '0 5px 0 #000', WebkitTextStroke: p.panel ? '0' : '3px black'}}>
                {l.text}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
