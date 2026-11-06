import React, {useEffect, useState} from 'react';
import {AbsoluteFill, continueRender, delayRender, Img, interpolate, OffthreadVideo, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

// Flat graphics: solid colour shapes, springs and wipes. Colours come from the brand file, the typeface is public/brand-font.ttf.
// scripts/remotion_gfx.py feeds the element list.

export type Brand = {accent: string; accent2: string; ink: string; paper: string};
export type El = {type: string; at: number; out?: number; x?: number; y?: number; layer?: 'front' | 'behind' | 'both'; [k: string]: any};
export type SceneProps = {frames: number; layer: 'front' | 'behind'; elements: El[]; brand: Brand};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const useFont = () => {
  const [h] = useState(() => delayRender('BrandFont'));
  useEffect(() => {
    const f = new FontFace('BrandFont', `url(${staticFile('brand-font.ttf')})`, {weight: '100 900'});
    f.load().then(() => {document.fonts.add(f); continueRender(h);}).catch(() => continueRender(h));
  }, [h]);
};
const pop = (lf: number, fps: number, soft = false) => spring({frame: Math.max(0, lf), fps, config: soft ? {damping: 22, stiffness: 110, mass: 0.8} : {damping: 13, stiffness: 190, mass: 0.6}});
const ease = (lf: number, a: number, b: number) => { const t = interpolate(lf, [a, b], [0, 1], clamp); return 1 - Math.pow(1 - t, 3); };
const leave = (frame: number, out: number | undefined, total: number) => interpolate(frame, [(out ?? total) - 5, out ?? total], [1, 0], clamp);

type P = {e: El; lf: number; brand: Brand; ex: number};

// --- glyphs: flat shapes in a 100 box; c = paper, h = second colour, k = ink ------------------------------------------------------------------
const Glyph: React.FC<{g: string; brand: Brand; t?: number}> = ({g, brand, t = 1}) => {
  const c = brand.paper, h = brand.accent2, k = brand.ink;
  const S: Record<string, React.ReactNode> = {
    fish: <><path d="M12 50 C28 22 64 22 80 50 C64 78 28 78 12 50 Z" fill={c} /><path d="M78 50 L96 33 L96 67 Z" fill={h} /><circle cx={30} cy={45} r={4.5} fill={k} /></>,
    heart: <path d="M50 84 C12 58 14 26 36 23 C44 22 49 27 50 34 C51 27 56 22 64 23 C86 26 88 58 50 84 Z" fill={c} />,
    bell: <><path d="M50 14 C34 14 28 28 28 42 L28 56 L19 67 L81 67 L72 56 L72 42 C72 28 66 14 50 14 Z" fill={c} /><circle cx={50} cy={78} r={8} fill={h} /></>,
    clock: <><circle cx={50} cy={50} r={36} fill={c} /><rect x={47.5} y={24} width={5} height={28} rx={2.5} fill={k} /><rect x={50} y={47.5} width={20} height={5} rx={2.5} fill={k} /></>,
    ban: <><circle cx={50} cy={50} r={34} fill="none" stroke={c} strokeWidth={10} /><rect x={22} y={45} width={56} height={10} rx={5} fill={c} transform="rotate(-45 50 50)" /></>,
    book: <><rect x={22} y={14} width={58} height={72} rx={5} fill={c} /><rect x={22} y={14} width={12} height={72} rx={4} fill={h} /><rect x={42} y={28} width={30} height={6} rx={3} fill={k} opacity={0.85} /><rect x={42} y={42} width={22} height={6} rx={3} fill={k} opacity={0.55} /></>,
    person: <><circle cx={50} cy={34} r={16} fill={c} /><path d="M20 86 C20 60 80 60 80 86 Z" fill={c} /></>,
    people: <><circle cx={36} cy={36} r={12} fill={c} /><path d="M12 82 C12 60 60 60 60 82 Z" fill={c} /><circle cx={68} cy={40} r={10} fill={h} /><path d="M50 82 C50 64 90 64 90 82 Z" fill={h} /></>,
    flag: <><rect x={26} y={12} width={7} height={76} rx={3} fill={c} /><path d="M33 16 H80 L68 34 L80 52 H33 Z" fill={h} /></>,
    camera: <><rect x={12} y={28} width={76} height={52} rx={10} fill={c} /><rect x={30} y={18} width={26} height={14} rx={4} fill={c} /><circle cx={50} cy={54} r={17} fill={k} /><circle cx={50} cy={54} r={9} fill={h} /></>,
    check: <><circle cx={50} cy={50} r={38} fill={c} /><path d="M29 52 L44 67 L72 33" fill="none" stroke={brand.accent} strokeWidth={11} strokeLinecap="round" strokeLinejoin="round" /></>,
    bread: <><path d="M12 58 C12 34 30 24 50 24 C70 24 88 34 88 58 L88 70 C88 75 84 78 79 78 L21 78 C16 78 12 75 12 70 Z" fill={c} /><path d="M33 36 L40 56 M49 31 L56 53 M65 36 L72 56" stroke={h} strokeWidth={7} strokeLinecap="round" fill="none" /></>,
    wrench: <><path d="M72 12 C58 12 49 24 52 38 L16 72 C12 76 12 83 17 87 C21 91 28 90 32 86 L66 52 C80 55 90 44 88 30 L74 42 L62 34 L58 20 Z" fill={c} /><circle cx={24} cy={78} r={5} fill={h} /></>,
    bulb: <><path d="M50 10 C31 10 20 25 20 40 C20 53 29 59 33 68 L67 68 C71 59 80 53 80 40 C80 25 69 10 50 10 Z" fill={c} /><rect x={35} y={72} width={30} height={9} rx={4.5} fill={h} /><rect x={40} y={85} width={20} height={7} rx={3.5} fill={h} /></>,
    star: <path d="M50 8 L62 37 L93 38 L68 57 L77 88 L50 70 L23 88 L32 57 L7 38 L38 37 Z" fill={c} />,
    spark: <path d="M50 8 L58 42 L92 50 L58 58 L50 92 L42 58 L8 50 L42 42 Z" fill={c} />,
    smile: <><circle cx={50} cy={50} r={36} fill={c} /><circle cx={38} cy={42} r={5} fill={k} /><circle cx={62} cy={42} r={5} fill={k} /><path d="M32 58 C40 74 60 74 68 58" fill="none" stroke={k} strokeWidth={6} strokeLinecap="round" /></>,
    bottle: <><rect x={42} y={10} width={16} height={18} rx={3} fill={h} /><path d="M34 30 H66 L72 40 V82 C72 88 68 90 64 90 H36 C32 90 28 88 28 82 V40 Z" fill={c} /><path d="M40 52 L60 72 M60 52 L40 72" stroke={k} strokeWidth={7} strokeLinecap="round" /></>,
    hammer: <><rect x={44} y={36} width={12} height={54} rx={4} fill={h} /><rect x={20} y={14} width={60} height={26} rx={6} fill={c} /></>,
    phone: <><rect x={28} y={8} width={44} height={84} rx={9} fill={c} /><rect x={34} y={18} width={32} height={60} rx={3} fill={h} /><circle cx={50} cy={85} r={3} fill={k} /></>,
    chat: <><path d="M12 20 H88 Q94 20 94 26 V64 Q94 70 88 70 H48 L28 88 V70 H12 Q6 70 6 64 V26 Q6 20 12 20 Z" fill={c} /><circle cx={30} cy={46} r={5} fill={k} /><circle cx={50} cy={46} r={5} fill={k} /><circle cx={70} cy={46} r={5} fill={k} /></>,
    route: <><path d="M14 80 C30 20 60 90 84 28" fill="none" stroke={c} strokeWidth={8} strokeLinecap="round" strokeDasharray="1 16" /><circle cx={14} cy={80} r={8} fill={c} /><path d="M84 12 C92 12 96 18 96 24 C96 32 84 44 84 44 C84 44 72 32 72 24 C72 18 76 12 84 12 Z" fill={h} /></>,
  };
  return <svg width="100%" height="100%" viewBox="0 0 100 100" style={{overflow: 'visible', opacity: t}}>{S[g]}</svg>;
};

const Plate: React.FC<{x: number; y: number; size: number; brand: Brand; lf: number; ex: number; shape?: 'circle' | 'square'; fill?: string; children?: React.ReactNode; tilt?: number; delay?: number}> = ({x, y, size, brand, lf, ex, shape = 'circle', fill, children, tilt = 0, delay = 0}) => {
  const {fps} = useVideoConfig();
  const s = pop(lf - delay, fps);
  return (
    <div style={{position: 'absolute', left: x - size / 2, top: y - size / 2, width: size, height: size, borderRadius: shape === 'circle' ? '50%' : size * 0.24, background: fill ?? brand.accent,
      transform: `scale(${(0.4 + 0.6 * s) * (0.9 + 0.1 * ex)}) rotate(${tilt + (1 - s) * -12}deg)`, opacity: ex * Math.min(1, s * 4)}}>{children}</div>
  );
};

const Label: React.FC<{text: string; x: number; y: number; lf: number; ex: number; brand: Brand; size?: number; delay?: number; dark?: boolean}> = ({text, x, y, lf, ex, brand, size = 40, delay = 0, dark}) => {
  const w = ease(lf - delay, 0, 10);
  return (
    <div style={{position: 'absolute', left: x - 520, width: 1040, top: y, display: 'flex', justifyContent: 'center', opacity: ex}}>
      <div style={{clipPath: `inset(0 ${(1 - w) * 100}% 0 0)`, background: dark ? brand.ink : brand.paper, color: dark ? brand.paper : brand.ink, fontFamily: 'BrandFont', fontWeight: 800, fontSize: size,
        letterSpacing: '-0.02em', padding: '8px 24px 12px', lineHeight: 1.05, whiteSpace: 'nowrap'}}>{text}</div>
    </div>
  );
};

// --- elements -----------------------------------------------------------------------------------------------------------------------
const BannerEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const w = ease(lf, 0, 12); const size = e.size ?? 64; const sw = e.strikeAt != null ? ease(lf - e.strikeAt, 0, 9) : 0;
  const swap = e.swapAt != null && lf >= e.swapAt;
  const txt = swap ? e.text2 : e.text;
  const bw = e.w ?? 760;
  return (
    <div style={{position: 'absolute', left: (e.x ?? 540) - bw / 2, top: e.y ?? 250, width: bw, opacity: ex}}>
      <div style={{background: swap ? brand.ink : brand.accent, clipPath: `inset(0 ${(1 - w) * 100}% 0 0)`, padding: '14px 30px 18px', transition: 'none'}}>
        <div style={{position: 'relative', display: 'inline-block', color: brand.paper, fontFamily: 'BrandFont', fontWeight: 800, fontSize: size, letterSpacing: '-0.03em', lineHeight: 1.05, whiteSpace: 'nowrap'}}>
          {txt}
          {sw > 0 && !swap && <div style={{position: 'absolute', left: -8, top: '54%', height: Math.max(8, size * 0.12), width: `calc(${sw * 100}% + 16px)`, background: brand.paper}} />}
        </div>
      </div>
      {e.sub && <div style={{marginTop: 8, display: 'inline-block', background: brand.paper, color: brand.ink, fontFamily: 'BrandFont', fontWeight: 800, fontSize: 30, padding: '4px 16px 6px', opacity: ease(lf, 8, 16)}}>{e.sub}</div>}
    </div>
  );
};

const PlateEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const size = e.size ?? 190; const cx = e.x ?? 540, cy = e.y ?? 400;
  return (
    <>
      <Plate x={cx} y={cy} size={size} brand={brand} lf={lf} ex={ex} shape={e.shape ?? 'circle'} fill={e.fill === 'ink' ? brand.ink : e.fill === 'paper' ? brand.paper : undefined} tilt={e.tilt ?? 0}>
        <div style={{position: 'absolute', inset: size * 0.14}}><Glyph g={e.glyph} brand={brand} /></div>
      </Plate>
      {e.label && <Label text={e.label} x={cx} y={cy + size / 2 + 14} lf={lf} ex={ex} brand={brand} delay={6} size={e.labelSize ?? 38} />}
    </>
  );
};

// a grid of tiles that pop in one by one; optionally crossed out one by one (accounts being deleted)
const TilesEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig();
  const cols = e.cols ?? 3, rows = e.rows ?? 2, sz = e.size ?? 96, gap = e.gap ?? 16;
  const cx = e.x ?? 540, cy = e.y ?? 400; const W = cols * sz + (cols - 1) * gap, H = rows * sz + (rows - 1) * gap;
  const out: React.ReactNode[] = [];
  const glyphs: string[] = e.glyphs ?? ['camera', 'heart', 'chat', 'bell', 'people', 'spark'];
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const i = r * cols + c; const s = pop(lf - (e.step ?? 4) * i, fps);
    const crossed = e.crossFrom != null && lf >= e.crossFrom + (e.crossStep ?? 5) * i;
    const cs = crossed ? ease(lf - (e.crossFrom + (e.crossStep ?? 5) * i), 0, 6) : 0;
    out.push(
      <div key={i} style={{position: 'absolute', left: cx - W / 2 + c * (sz + gap), top: cy - H / 2 + r * (sz + gap), width: sz, height: sz, borderRadius: sz * 0.24,
        background: crossed ? `${brand.accent}55` : brand.accent, transform: `scale(${(0.3 + 0.7 * s) * (1 - 0.1 * cs)})`, opacity: ex * Math.min(1, s * 4)}}>
        <div style={{position: 'absolute', inset: sz * 0.18, opacity: 1 - 0.7 * cs}}><Glyph g={glyphs[i % glyphs.length]} brand={brand} /></div>
        {crossed && <svg width={sz} height={sz} viewBox="0 0 100 100" style={{position: 'absolute', inset: 0}}><path d="M24 24 L76 76 M76 24 L24 76" stroke={brand.ink} strokeWidth={12} strokeLinecap="round" strokeDasharray="1" pathLength={1} strokeDashoffset={1 - cs} /></svg>}
      </div>
    );
  }
  return <>{out}{e.label && <Label text={e.label} x={cx} y={cy + H / 2 + 16} lf={lf} ex={ex} brand={brand} delay={8} size={e.labelSize ?? 38} />}</>;
};

// a heart plate with a number that ticks up, and bell badges that appear (likes / interactions)
const CounterEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig();
  const cx = e.x ?? 540, cy = e.y ?? 400; const n = Math.round(interpolate(lf, [e.countFrom ?? 4, e.countTo ?? 50], [0, e.max ?? 248], clamp));
  const beat = 1 + 0.06 * Math.max(0, Math.sin(lf / 2.2));
  const s = pop(lf, fps);
  return (
    <>
      <div style={{position: 'absolute', left: cx - 280, top: cy - 90, width: 560, height: 180, borderRadius: 90, background: brand.accent, opacity: ex * Math.min(1, s * 4), transform: `scale(${0.8 + 0.2 * s})`}}>
        <div style={{position: 'absolute', left: 26, top: 26, width: 128, height: 128, transform: `scale(${beat})`}}><Glyph g="heart" brand={brand} /></div>
        <div style={{position: 'absolute', left: 170, top: 0, height: 180, display: 'flex', alignItems: 'center', fontFamily: 'BrandFont', fontWeight: 800, fontSize: 112, color: brand.paper, letterSpacing: '-0.04em'}}>{n}</div>
      </div>
      {(e.badges ?? []).map((b: {at: number; dx: number; dy: number; n: number}, i: number) => {
        const bs = pop(lf - b.at, fps);
        return <div key={i} style={{position: 'absolute', left: cx + b.dx - 38, top: cy + b.dy - 38, width: 76, height: 76, borderRadius: '50%', background: brand.paper, color: brand.accent, fontFamily: 'BrandFont', fontWeight: 800, fontSize: 40,
          display: 'flex', alignItems: 'center', justifyContent: 'center', transform: `scale(${bs})`, opacity: ex * Math.min(1, bs * 4)}}>{b.n}</div>;
      })}
      {e.label && <Label text={e.label} x={cx} y={cy + 108} lf={lf} ex={ex} brand={brand} delay={8} size={36} />}
    </>
  );
};


// a clock whose hands spin fast ("multiple hours" slipping away)
const ClockEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig(); const s = pop(lf, fps); const cx = e.x ?? 540, cy = e.y ?? 400; const size = e.size ?? 200;
  const spin = interpolate(lf, [0, e.dur ?? 40], [0, 360 * 3], clamp);
  return (
    <>
      <div style={{position: 'absolute', left: cx - size / 2, top: cy - size / 2, width: size, height: size, borderRadius: '50%', background: brand.accent, opacity: ex * Math.min(1, s * 4), transform: `scale(${0.5 + 0.5 * s})`}}>
        <svg width={size} height={size} viewBox="0 0 100 100"><circle cx={50} cy={50} r={36} fill={brand.paper} />
          <rect x={47.5} y={24} width={5} height={28} rx={2.5} fill={brand.ink} transform={`rotate(${spin} 50 50)`} /><rect x={47.5} y={32} width={5} height={20} rx={2.5} fill={brand.accent} transform={`rotate(${spin / 12} 50 50)`} /><circle cx={50} cy={50} r={4} fill={brand.ink} /></svg>
      </div>
      {e.label && <Label text={e.label} x={cx} y={cy + size / 2 + 14} lf={lf} ex={ex} brand={brand} delay={6} size={36} />}
    </>
  );
};



// a round stamp ("No.")
const StampEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig(); const s = spring({frame: Math.max(0, lf), fps, config: {damping: 9, stiffness: 260, mass: 0.5}}); const size = e.size ?? 210;
  return (
    <div style={{position: 'absolute', left: (e.x ?? 540) - size / 2, top: (e.y ?? 400) - size / 2, width: size, height: size, borderRadius: '50%', background: brand.accent, display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontFamily: 'BrandFont', fontWeight: 800, fontSize: size * 0.4, color: brand.paper, letterSpacing: '-0.03em', transform: `rotate(${e.rotate ?? -10}deg) scale(${(1.6 - 0.6 * s) * (0.9 + 0.1 * ex)})`, opacity: ex * Math.min(1, s * 3)}}>{e.text}</div>
  );
};


// stairs with a dot that climbs to a flag (the next step, long-term goals)
const StepsEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig(); const cx = e.x ?? 540, cy = e.y ?? 420; const sw = 120, sh = 70;
  const climb = ease(lf - (e.climbFrom ?? 8), 0, e.climbDur ?? 40);
  const xs = [0, 1, 2].map((i) => cx - 180 + sw * (i + 0.5)), ys = [0, 1, 2].map((i) => cy + 120 - sh * (i + 1) - 24);
  const f = Math.min(1.999, climb * 2); const i0 = Math.floor(f); const u = f - i0;
  const px = xs[i0] + (xs[i0 + 1] - xs[i0]) * u, py = ys[i0] + (ys[i0 + 1] - ys[i0]) * u - Math.sin(u * Math.PI) * 24;
  const flag = pop(lf - (e.flagAt ?? 9999), fps);
  return (
    <>
      {[0, 1, 2].map((i) => { const g = pop(lf - i * 3, fps); return <div key={i} style={{position: 'absolute', left: cx - 180 + sw * i, top: cy + 120 - sh * (i + 1), width: sw, height: sh * (i + 1), background: [brand.accent2, brand.accent, brand.accent][i],
        opacity: ex * Math.min(1, g * 4), transform: `translateY(${(1 - g) * 40}px)`, borderRadius: '10px 10px 0 0'}} />; })}
      <div style={{position: 'absolute', left: px - 20, top: py - 20, width: 40, height: 40, borderRadius: '50%', background: brand.paper, opacity: ex}} />
      {lf >= (e.flagAt ?? 9999) && <div style={{position: 'absolute', left: xs[2] + 14, top: ys[2] - 110, width: 90, height: 90, transform: `scale(${flag})`, transformOrigin: 'left bottom', opacity: ex}}><Glyph g="flag" brand={{...brand, paper: brand.accent}} /></div>}
      {e.label && <Label text={e.label} x={cx} y={cy + 140} lf={lf} ex={ex} brand={brand} delay={4} size={36} />}
    </>
  );
};

// word chips that slide up one by one (Authentic, Get to know me, ...)
const ChipsEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig();
  const items: {t: string; at: number; x: number; y: number; dark?: boolean; glyph?: string}[] = e.items;
  return <>{items.map((it, i) => {
    const s = pop(lf - it.at, fps);
    return (
      <div key={i} style={{position: 'absolute', left: it.x - 300, width: 600, top: it.y, display: 'flex', justifyContent: 'center', opacity: ex * Math.min(1, s * 4), transform: `translateY(${(1 - s) * 40}px)`}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 12, background: it.dark ? brand.ink : brand.accent, color: brand.paper, fontFamily: 'BrandFont', fontWeight: 800, fontSize: 46, letterSpacing: '-0.02em', padding: '10px 26px 14px 18px', borderRadius: 60, lineHeight: 1}}>
          {it.glyph && <div style={{width: 52, height: 52}}><Glyph g={it.glyph} brand={brand} /></div>}{it.t}
        </div>
      </div>
    );
  })}</>;
};


// a toggle that flips from one word to the other ("depends on how you use it")
const ToggleEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig(); const s = pop(lf, fps); const cx = e.x ?? 540, cy = e.y ?? 420;
  const flip = pop(lf - (e.flipAt ?? 30), fps, true); const f = Math.min(1, Math.max(0, flip));
  return (
    <div style={{position: 'absolute', inset: 0, opacity: ex * Math.min(1, s * 4)}}>
      <div style={{position: 'absolute', left: cx - 190, top: cy - 62, width: 380, height: 124, borderRadius: 62, background: f > 0.5 ? brand.accent : brand.ink, transform: `scale(${0.7 + 0.3 * s})`}}>
        <div style={{position: 'absolute', left: 12 + f * 256, top: 12, width: 100, height: 100, borderRadius: '50%', background: brand.paper}} />
      </div>
      <Label text={e.l1 ?? 'A'} x={cx - 190} y={cy + 80} lf={lf} ex={ex * (f > 0.5 ? 0.35 : 1)} brand={brand} delay={4} size={34} dark />
      <Label text={e.l2 ?? 'B'} x={cx + 190} y={cy + 80} lf={lf} ex={ex * (f > 0.5 ? 1 : 0.35)} brand={brand} delay={4} size={34} />
    </div>
  );
};

// a Follow button that is tapped and turns into Following
const FollowEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig(); const s = pop(lf, fps); const cx = e.x ?? 540, cy = e.y ?? 420; const tap = lf >= (e.tapAt ?? 24);
  const ring = interpolate(lf, [(e.tapAt ?? 24), (e.tapAt ?? 24) + 14], [0, 1], clamp);
  const press = lf >= (e.tapAt ?? 24) && lf < (e.tapAt ?? 24) + 4 ? 0.93 : 1;
  return (
    <div style={{position: 'absolute', inset: 0, opacity: ex * Math.min(1, s * 4)}}>
      <div style={{position: 'absolute', left: cx - 230, top: cy - 62, width: 460, height: 124, borderRadius: 62, background: tap ? brand.paper : brand.accent, color: tap ? brand.ink : brand.paper, fontFamily: 'BrandFont', fontWeight: 800, fontSize: 64,
        letterSpacing: '-0.03em', display: 'flex', alignItems: 'center', justifyContent: 'center', transform: `scale(${(0.6 + 0.4 * s) * press})`}}>{tap ? (e.done ?? 'Following') : (e.text ?? 'Follow')}</div>
      {ring > 0 && ring < 1 && <div style={{position: 'absolute', left: cx + 120 - 30 - ring * 60, top: cy - 30 - ring * 60, width: 60 + ring * 120, height: 60 + ring * 120, borderRadius: '50%', background: `${brand.accent}`, opacity: (1 - ring) * 0.55}} />}
    </div>
  );
};

// a comment bubble: three dots, then the message
const BubbleEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig(); const s = pop(lf, fps); const cx = e.x ?? 540, cy = e.y ?? 420; const msgAt = e.msgAt ?? 22;
  const w = e.w ?? 640;
  return (
    <div style={{position: 'absolute', inset: 0, opacity: ex * Math.min(1, s * 4), transform: `scale(${e.scale ?? 1})`, transformOrigin: `${cx}px ${cy}px`}}>
      <div style={{position: 'absolute', left: cx - w / 2, top: cy - 70, width: w, height: 140, borderRadius: 70, background: brand.accent, transform: `scale(${0.6 + 0.4 * s})`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'BrandFont', fontWeight: 800, color: brand.paper}}>
        {lf < msgAt ? [0, 1, 2].map((i) => <div key={i} style={{width: 26, height: 26, borderRadius: '50%', background: brand.paper, margin: '0 10px', transform: `translateY(${-Math.max(0, Math.sin((lf - i * 3) / 3)) * 14}px)`}} />)
          : <span style={{fontSize: e.size ?? 52, letterSpacing: '-0.03em', opacity: ease(lf - msgAt, 0, 6)}}>{e.text}</span>}
      </div>
      <div style={{position: 'absolute', left: cx - w / 2 + 70, top: cy + 62, width: 0, height: 0, borderLeft: '26px solid transparent', borderRight: '26px solid transparent', borderTop: `34px solid ${brand.accent}`, transform: `scale(${0.6 + 0.4 * s})`}} />
    </div>
  );
};

// a giant flat word or mark BEHIND the speaker (rendered on the behind layer, punched by the matte)
const BehindWordEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig(); const s = pop(lf, fps, true); const size = e.size ?? 300;
  return (
    <div style={{position: 'absolute', left: (e.x ?? 540) - 540, width: 1080, top: (e.y ?? 600) - size * 0.78, textAlign: 'center', fontFamily: 'BrandFont', fontWeight: 800, fontSize: size, lineHeight: 1, letterSpacing: '-0.05em',
      color: e.color === 'ink' ? brand.ink : e.color === 'paper' ? brand.paper : brand.accent, opacity: ex * Math.min(1, s * 3) * (e.opacity ?? 1), transform: `translateY(${(1 - s) * 90}px) rotate(${e.rotate ?? 0}deg)`, whiteSpace: 'nowrap'}}>{e.text}</div>
  );
};


// --- a video BEHIND the speaker. Full frame, or the TOP of the frame only: `splitY` / `splitFade` fade it out into the real background (a split greenscreen);
//     `h` is the height the clip is fitted into, `pos` its crop position.
const BgVideoEl: React.FC<P> = ({e, lf, ex}) => {
  const sy = e.splitY, sf = e.splitFade ?? 300;
  const mask = sy ? `linear-gradient(to bottom, #000 0px, #000 ${sy}px, rgba(0,0,0,0.65) ${sy + sf * 0.3}px, rgba(0,0,0,0.2) ${sy + sf * 0.7}px, transparent ${sy + sf}px)` : undefined;
  const s = pop(lf, 30, true);
  return (
    <Sequence from={e.at} layout="none">
      <AbsoluteFill style={{opacity: ex * Math.min(1, lf / 5), WebkitMaskImage: mask, maskImage: mask, filter: `brightness(${e.brightness ?? 1})`, transform: `scale(${1 + (1 - s) * 0.04})`, transformOrigin: '540px 400px'}}>
        <OffthreadVideo src={staticFile(e.src)} muted startFrom={e.skip ?? 0} style={{position: 'absolute', left: 0, top: 0, width: 1080, height: e.h ?? 1920, objectFit: 'cover', objectPosition: e.pos ?? '50% 50%'}} />
      </AbsoluteFill>
    </Sequence>
  );
};

// --- the hook as big flat blocks that slam in on the words (a bold poster headline, not a thin bar): words [{t, at, bg, fg, rot, dx}] ---------------------------------------
const HookStackEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig();
  const size = e.size ?? 118, words: any[] = e.words ?? [];
  const col = (n?: string) => (n === 'paper' ? brand.paper : n === 'ink' ? brand.ink : n === 'haze' ? brand.accent2 : brand.accent);
  return (
    <div style={{position: 'absolute', left: 0, width: 1080, top: e.y ?? 240, opacity: ex, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: e.gap ?? size * 0.06}}>
      {words.map((w, i) => {
        const l = lf - w.at; const sp = l < 0 ? 0 : spring({frame: l, fps, config: {damping: 12, stiffness: 240, mass: 0.55}});
        const wipe = ease(l, 0, 9);
        return (
          <div key={i} style={{transform: `translateX(${(w.dx ?? 0) + (1 - sp) * (i % 2 ? 160 : -160)}px) rotate(${(w.rot ?? 0) * sp}deg) scale(${0.8 + 0.2 * sp})`, opacity: l < 0 ? 0 : 1,
            clipPath: `inset(-40% ${(1 - wipe) * 100}% -40% 0)`, background: col(w.bg), color: col(w.fg ?? 'paper'), fontFamily: 'BrandFont', fontWeight: 800, fontSize: size, lineHeight: 1,
            letterSpacing: '-0.04em', padding: `${size * 0.1}px ${size * 0.3}px ${size * 0.17}px`, borderRadius: size * 0.16, whiteSpace: 'nowrap'}}>{w.t}</div>
        );
      })}
    </div>
  );
};




// --- a photo card: the SAME box for every picture (same size, same proportions: the image is fitted into it, never stretched), a solid accent backing, a name tag ----
const PhotoCardEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig(); const s = pop(lf, fps);
  const w = e.w ?? 300, h = e.h ?? 400, cx = e.x ?? 200, cy = e.y ?? 760, tilt = e.tilt ?? 0;
  return (
    <div style={{position: 'absolute', inset: 0, opacity: ex * Math.min(1, s * 4)}}>
      <div style={{position: 'absolute', left: cx - w / 2, top: cy - h / 2, width: w, height: h, transform: `scale(${(0.5 + 0.5 * s) * (0.94 + 0.06 * ex)}) rotate(${tilt + (1 - s) * -5}deg)`}}>
        <div style={{position: 'absolute', left: -14, top: 14, width: w, height: h, borderRadius: 34, background: brand.accent}} />
        <div style={{position: 'absolute', left: 0, top: 0, width: w, height: h, borderRadius: 34, overflow: 'hidden', background: brand.paper}}>
          <Img src={staticFile(e.src)} style={{width: '100%', height: '100%', objectFit: 'cover', objectPosition: e.pos ?? '50% 10%'}} />
        </div>
        {e.label && <div style={{position: 'absolute', left: w / 2, bottom: -30, transform: 'translateX(-50%)', background: brand.ink, color: brand.paper, fontFamily: 'BrandFont', fontWeight: 800, fontSize: 36, letterSpacing: '-0.02em', padding: '6px 24px 10px', borderRadius: 30, lineHeight: 1.05, whiteSpace: 'nowrap', opacity: ease(lf, 6, 14)}}>{e.label}</div>}
      </div>
    </div>
  );
};



// --- a pair of icon plates (e.g. bread + wrench) that land on their own words: items [{g, at, ink?}] -----------------------------------------------------------------
const PairIconsEl: React.FC<P> = ({e, lf, brand, ex}) => {
  const {fps} = useVideoConfig();
  const cx = e.x ?? 540, cy = e.y ?? 330, size = e.size ?? 170, gap = e.gap ?? 90;
  const items: {g: string; at: number; ink?: boolean}[] = e.items ?? [];
  return <>{items.map((it, i) => {
    const x = cx + (i - (items.length - 1) / 2) * (size + gap);
    return (
      <Plate key={i} x={x} y={cy} size={size} brand={brand} lf={lf} ex={ex} fill={it.ink ? brand.ink : brand.accent} tilt={i % 2 ? 4 : -4} delay={it.at}>
        <div style={{position: 'absolute', inset: size * 0.2}}><Glyph g={it.g} brand={brand} /></div>
      </Plate>
    );
  })}</>;
};

export const SceneFlat: React.FC<SceneProps> = ({frames, layer, elements, brand}) => {
  useFont();
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      {elements.filter((x) => (x.layer ?? 'front') === layer || x.layer === 'both').map((x, i) => {
        const lf = frame - x.at; if (lf < 0) return null;
        const ex = leave(frame, x.out, frames); if (ex <= 0) return null;
        const p = {e: x, lf, brand, ex};
        switch (x.type) {
          case 'banner': return <BannerEl key={i} {...p} />;
          case 'plate': return <PlateEl key={i} {...p} />;
          case 'tiles': return <TilesEl key={i} {...p} />;
          case 'counter': return <CounterEl key={i} {...p} />;
          case 'clock': return <ClockEl key={i} {...p} />;
          case 'stamp': return <StampEl key={i} {...p} />;
          case 'steps': return <StepsEl key={i} {...p} />;
          case 'chips': return <ChipsEl key={i} {...p} />;
          case 'toggle': return <ToggleEl key={i} {...p} />;
          case 'follow': return <FollowEl key={i} {...p} />;
          case 'bubble': return <BubbleEl key={i} {...p} />;
          case 'pairicons': return <PairIconsEl key={i} {...p} />;
          case 'photocard': return <PhotoCardEl key={i} {...p} />;
          case 'bgvideo': return <BgVideoEl key={i} {...p} />;
          case 'hookstack': return <HookStackEl key={i} {...p} />;
          case 'behindword': return <BehindWordEl key={i} {...p} />;
          default: return null;
        }
      })}
    </AbsoluteFill>
  );
};
