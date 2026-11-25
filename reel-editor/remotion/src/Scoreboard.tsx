import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {BLUE, GREEN, RED, GOLD, PANEL, money, easeOut, totalAt, fadeInOut, useFonts} from './theme';

type Row = {t: number; label: string; value?: number; text?: string};
export type ScoreboardProps = {
  dur: number; x: number; y: number; w: number; rowH: number;
  title: string; totalLabel: string; goal?: number; rows: Row[];
};

export const scoreboardDefaults: ScoreboardProps = {
  dur: 14, x: 40, y: 470, w: 500, rowH: 58, title: '2026 · YEAR 1', totalLabel: 'RUNNING TOTAL', goal: 1000000,
  rows: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November']
    .map((m, i) => ({t: 1 + i * 0.7, label: m, value: [0, 107717, 55000, 0, 41000, 91500, 133689, 30000, 87000, 50000, 230800][i]}))
    .concat([{t: 9.5, label: 'December', text: '??'} as any]),
};

export const Scoreboard: React.FC<ScoreboardProps> = (p) => {
  useFonts();
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const rows = p.rows.map((r) => ({...r, f: Math.round(r.t * fps)}));
  const head = p.goal ? 262 : 214;
  const pad = 26;
  const durF = Math.round(p.dur * fps);
  // panel grows one row at a time as months land (starts as just the header + $0)
  const grown = rows.reduce((a, r) => a + (frame >= r.f ? spring({frame: frame - r.f, fps,
    config: {damping: 20, stiffness: 160}}) : 0), 0);
  const panelH = head + p.rowH * grown + (grown > 0 ? 24 * Math.min(1, grown) : 0) + 6;

  const enter = spring({frame, fps, config: {damping: 16, stiffness: 140}});
  const opacity = fadeInOut(frame, durF);
  const total = totalAt(rows, frame);
  const lastLanded = rows.filter((r) => frame >= r.f).pop();
  const rolling = rows.some((r) => r.value && frame >= r.f && frame < r.f + 21);
  const pop = lastLanded && lastLanded.value
    ? spring({frame: frame - lastLanded.f, fps, config: {damping: 9, stiffness: 220}}) : 1;
  const totalScale = rolling ? 1 + 0.08 * Math.sin(Math.min(1, (frame - (lastLanded?.f ?? 0)) / 21) * Math.PI) : 1;

  // highlight bar glides from row to row
  let hiY = -1;
  rows.forEach((r, i) => {
    if (frame < r.f) return;
    const s = spring({frame: frame - r.f, fps, config: {damping: 18, stiffness: 170}});
    const prev = i === 0 ? head - p.rowH : head + (i - 1) * p.rowH;
    hiY = hiY < 0 ? prev + (head + i * p.rowH - prev) * s : hiY + p.rowH * s;
  });
  const curIdx = rows.reduce((a, r, i) => (frame >= r.f ? i : a), -1);
  const goalFrac = p.goal ? Math.min(1, total / p.goal) : 0;

  return (
    <AbsoluteFill style={{opacity}}>
      <div style={{
        position: 'absolute', left: p.x, top: p.y, width: p.w, height: panelH, borderRadius: 30,
        background: PANEL, border: `4px solid ${BLUE}`, boxShadow: '0 18px 50px rgba(0,0,0,0.55)', overflow: 'hidden',
        transform: `translateX(${(1 - enter) * -60}px) scale(${0.94 + 0.06 * enter})`, transformOrigin: 'left center',
      }}>
        <div style={{position: 'absolute', top: 18, width: '100%', textAlign: 'center', fontFamily: 'MontBlack',
                     fontSize: 30, color: 'white', letterSpacing: 2}}>{p.title}</div>
        <div style={{position: 'absolute', top: 62, width: '100%', textAlign: 'center', fontFamily: 'MontXB',
                     fontSize: 22, color: '#AAB0BA', letterSpacing: 3}}>{p.totalLabel}</div>
        <div style={{position: 'absolute', top: 92, width: '100%', textAlign: 'center', fontFamily: 'MontBlack',
                     fontSize: 70, color: rolling ? GREEN : 'white', fontVariantNumeric: 'tabular-nums',
                     transform: `scale(${totalScale})`, textShadow: rolling ? `0 0 28px ${GREEN}88` : 'none'}}>
          {money(total)}
        </div>
        {/* "+$52,217" chip floats up from the total when a month lands */}
        {lastLanded && lastLanded.value !== undefined && frame - lastLanded.f < 26 ? (
          <div style={{position: 'absolute', left: 26, top: 236 - 10 * easeOut(frame, lastLanded.f, 26),
                       fontFamily: 'MontBlack', fontSize: 22, opacity: 1 - easeOut(frame, lastLanded.f + 14, 12),
                       color: lastLanded.value ? GREEN : RED}}>
            {lastLanded.value ? '+' + money(lastLanded.value) : '+$0'}
          </div>
        ) : null}
        {p.goal ? (
          <>
            <div style={{position: 'absolute', left: pad, right: pad, top: 186, height: 18, borderRadius: 9,
                         background: 'rgba(255,255,255,0.14)'}} />
            <div style={{position: 'absolute', left: pad, top: 186, height: 18, borderRadius: 9, background: BLUE,
                         width: Math.max(18, (p.w - 2 * pad) * goalFrac), boxShadow: `0 0 18px ${BLUE}`}} />
            <div style={{position: 'absolute', right: pad, top: 212, fontFamily: 'MontXB', fontSize: 22,
                         color: '#D8DCE2'}}>{Math.round(goalFrac * 100)}% OF {money(p.goal)}</div>
          </>
        ) : null}
        {hiY >= 0 ? (
          <div style={{position: 'absolute', left: 10, right: 10, top: hiY + 4, height: p.rowH - 8, borderRadius: 14,
                       background: BLUE, opacity: 0.85}} />
        ) : null}
        {rows.map((r, i) => {
          if (frame < r.f) return null;
          const s = spring({frame: frame - r.f, fps, config: {damping: 14, stiffness: 180}});
          const top = head + i * p.rowH;
          const v = r.value !== undefined ? r.value * easeOut(frame, r.f, 14) : 0;
          const pulse = r.text ? 0.6 + 0.4 * (0.5 + 0.5 * Math.sin((frame - r.f) / 4)) : 1;
          return (
            <div key={i} style={{position: 'absolute', left: pad, right: pad, top, height: p.rowH, display: 'flex',
                                 alignItems: 'center', justifyContent: 'space-between', opacity: s,
                                 transform: `translateX(${(1 - s) * -36}px)`,
                                 background: i % 2 === 0 && i !== curIdx ? 'rgba(255,255,255,0.05)' : 'transparent'}}>
              <span style={{fontFamily: 'MontXB', fontSize: p.rowH * 0.48, color: 'white'}}>{r.label}</span>
              <span style={{fontFamily: 'MontBlack', fontSize: p.rowH * 0.5, fontVariantNumeric: 'tabular-nums',
                            color: r.text ? GOLD : r.value === 0 ? RED : 'white', opacity: pulse}}>
                {r.text ?? money(v)}
              </span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
