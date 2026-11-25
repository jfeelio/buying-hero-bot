import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {BLUE, GREEN, RED, PANEL, money, easeOut, totalAt, fadeInOut, useFonts} from './theme';

type Step = {t: number; label: string; value: number};
export type MeterProps = {dur: number; y: number; goal: number; title: string; pinned?: string[]; steps: Step[]};

export const meterDefaults: MeterProps = {
  dur: 14, y: 250, goal: 1000000, title: 'ROAD TO $1M', pinned: ['$826K IN 11 MONTHS', 'CAN I HIT $1M?'],
  steps: ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV']
    .map((m, i) => ({t: 1 + i * 0.7, label: m, value: [0, 107717, 55000, 0, 41000, 91500, 133689, 30000, 87000, 50000, 230800][i]})),
};

const short = (v: number) => (v >= 1000 ? `$${Math.round(v / 1000)}K` : `$${v}`);

/** Ceiling-height goal meter: pinned headline, big rolling total, $1M bar and a 12-month chip grid lighting up. */
export const GoalMeter: React.FC<MeterProps> = (p) => {
  useFonts();
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const steps = p.steps.map((s) => ({...s, f: Math.round(s.t * fps)}));
  const durF = Math.round(p.dur * fps);
  const opacity = fadeInOut(frame, durF);
  const total = totalAt(steps, frame);
  const last = steps.filter((s) => frame >= s.f).pop();
  const rolling = steps.some((s) => s.value && frame >= s.f && frame < s.f + 21);
  const frac = Math.min(1, total / p.goal);
  const enter = spring({frame, fps, config: {damping: 15, stiffness: 140}});
  const months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
  return (
    <AbsoluteFill style={{opacity}}>
      {p.pinned ? (
        <div style={{position: 'absolute', top: p.y - 190, left: 40, right: 40, textAlign: 'center', fontFamily: 'MontBlack',
                     lineHeight: 1.08, textShadow: '0 5px 0 #000, 0 0 16px rgba(0,0,0,0.6)', WebkitTextStroke: '3px black',
                     transform: `translateY(${(1 - enter) * -30}px)`}}>
          {p.pinned.map((l, i) => (
            <div key={i} style={{fontSize: i === 0 ? 64 : 76, color: i === 0 ? 'white' : '#FFD23C'}}>{l}</div>
          ))}
        </div>
      ) : null}
      <div style={{position: 'absolute', top: p.y, left: 60, right: 60, height: 470, borderRadius: 34, background: PANEL,
                   border: `4px solid ${BLUE}`, boxShadow: '0 18px 50px rgba(0,0,0,0.5)',
                   transform: `scale(${0.92 + 0.08 * enter})`}}>
        <div style={{position: 'absolute', top: 20, width: '100%', textAlign: 'center', fontFamily: 'MontBlack', fontSize: 34,
                     color: 'white', letterSpacing: 3}}>{p.title}</div>
        <div style={{position: 'absolute', top: 64, width: '100%', textAlign: 'center', fontFamily: 'MontBlack', fontSize: 116,
                     color: rolling ? GREEN : 'white', fontVariantNumeric: 'tabular-nums',
                     textShadow: rolling ? `0 0 34px ${GREEN}99` : 'none',
                     transform: `scale(${rolling ? 1.05 : 1})`}}>{money(total)}</div>
        <div style={{position: 'absolute', left: 40, right: 40, top: 210, height: 26, borderRadius: 13,
                     background: 'rgba(255,255,255,0.14)'}} />
        <div style={{position: 'absolute', left: 40, top: 210, height: 26, borderRadius: 13, background: BLUE,
                     width: Math.max(26, (960 - 80 - 80) * frac), boxShadow: `0 0 22px ${BLUE}`}} />
        <div style={{position: 'absolute', right: 40, top: 244, fontFamily: 'MontXB', fontSize: 26, color: '#D8DCE2'}}>
          {Math.round(frac * 100)}% OF {money(p.goal)}
        </div>
        {last ? (
          <div style={{position: 'absolute', left: 40, top: 244, fontFamily: 'MontBlack', fontSize: 26,
                       color: last.value ? GREEN : RED, opacity: easeOut(frame, last.f, 6)}}>
            {last.label} {last.value ? '+' + money(last.value) : '$0'}
          </div>
        ) : null}
        <div style={{position: 'absolute', left: 30, right: 30, top: 290, display: 'grid',
                     gridTemplateColumns: 'repeat(6, 1fr)', gap: 10}}>
          {months.map((m, i) => {
            const s = steps.find((x) => x.label === m);
            const on = s && frame >= s.f;
            const k = s ? spring({frame: frame - s.f, fps, config: {damping: 10, stiffness: 200}}) : 0;
            return (
              <div key={m} style={{height: 74, borderRadius: 14, display: 'flex', flexDirection: 'column',
                                   alignItems: 'center', justifyContent: 'center',
                                   background: on ? (s!.value ? BLUE : RED) : 'rgba(255,255,255,0.08)',
                                   transform: `scale(${on ? 0.85 + 0.15 * k : 1})`}}>
                <span style={{fontFamily: 'MontBlack', fontSize: 21, color: 'white', opacity: 0.85}}>{m}</span>
                <span style={{fontFamily: 'MontBlack', fontSize: 25, color: 'white'}}>
                  {on ? short(s!.value) : m === 'DEC' ? '??' : ''}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
