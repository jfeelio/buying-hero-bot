import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';
import {GOLD, fadeInOut, useFonts} from './theme';

// Spoken-hook title: the set-up words pop in on their cues, then the big number counts up and slams in.
//   lead: [{text, t}]  small white words, each springs in at t (s)
//   number: {from, to, t, prefix?, suffix?, label?}  counts from->to over 0.45 s starting at t, then holds with a pulse
export type HookProps = {
  dur: number; y: number; numSize?: number; leadSize?: number;
  lead: {text: string; t: number}[];
  number: {to: number; t: number; from?: number; prefix?: string; suffix?: string; words?: string};
};

export const hookDefaults: HookProps = {
  dur: 1.9, y: 1330,
  lead: [{text: 'CAN', t: 0.08}, {text: 'I', t: 0.5}, {text: 'MAKE', t: 0.6}, {text: 'IT', t: 0.84}, {text: 'TO', t: 0.92}],
  number: {to: 1000000, t: 1.0, prefix: '$', suffix: '?'},
};

export const HookTitle: React.FC<HookProps> = (p) => {
  useFonts();
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const durF = Math.round(p.dur * fps);
  const out = 1 - interpolate(frame, [durF - 4, durF], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const nf = Math.round(p.number.t * fps);
  const count = interpolate(frame, [nf, nf + Math.round(0.45 * fps)], [p.number.from ?? 0, p.number.to],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const slam = spring({frame: frame - nf, fps, config: {damping: 9, stiffness: 210}});
  const landed = frame >= nf + Math.round(0.45 * fps);
  const pulse = landed ? 1 + 0.04 * Math.sin((frame - nf) / 3) : 1;
  const num = p.number.words && landed ? p.number.words
    : (p.number.prefix ?? '') + Math.round(count).toLocaleString('en-US');
  return (
    <AbsoluteFill style={{opacity: out}}>
      <div style={{position: 'absolute', top: p.y, left: 0, right: 0, transform: 'translateY(-50%)', textAlign: 'center'}}>
        <div style={{display: 'flex', justifyContent: 'center', gap: 22, fontFamily: 'MontBlack', fontSize: p.leadSize ?? 70,
                     color: 'white', WebkitTextStroke: '4px black', paintOrder: 'stroke fill',
                     textShadow: '0 6px 0 #000'}}>
          {p.lead.map((w, i) => {
            const s = spring({frame: frame - Math.round(w.t * fps), fps, config: {damping: 12, stiffness: 220}});
            return (
              <span key={i} style={{opacity: Math.min(1, s * 1.5), transform: `translateY(${(1 - s) * 24}px) scale(${0.7 + 0.3 * s})`,
                                    display: 'inline-block'}}>{w.text}</span>
            );
          })}
        </div>
        {frame >= nf ? (
          <div style={{marginTop: 6, fontFamily: 'MontBlack', fontSize: p.numSize ?? 150, lineHeight: 1, color: GOLD,
                       fontVariantNumeric: 'tabular-nums', WebkitTextStroke: '6px black', paintOrder: 'stroke fill',
                       textShadow: `0 8px 0 #000, 0 0 40px ${GOLD}88`,
                       transform: `scale(${(0.55 + 0.45 * slam) * pulse}) rotate(${(1 - slam) * -6}deg)`}}>
            {num}{landed ? p.number.suffix ?? '' : ''}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
