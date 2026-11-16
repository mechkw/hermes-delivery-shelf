// Delivery Shelf — urban launch film. Deterministic: renderFrame(i) draws frame i at 30fps.
'use strict';
const W = 1920, H = 1080, FPS = 30;
const C = document.getElementById('c');
const ctx = C.getContext('2d');
const COL = { blk: '#0a0a0b', ink: '#131315', cream: '#ece4d4', y: '#f4c542', blue: '#2f6bff', red: '#e5412d', grey: '#26262b', dim: '#7a7366' };

// ---------- math ----------
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const lerp = (a, b, t) => a + (b - a) * t;
const eo = t => 1 - Math.pow(1 - clamp(t), 3);
const eo5 = t => 1 - Math.pow(1 - clamp(t), 5);
const ei = t => Math.pow(clamp(t), 3);
const eio = t => { t = clamp(t); return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
const eback = t => { t = clamp(t); const c1 = 2.2, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); };
const B0 = 0.093, BP = 0.6009;
const bt = n => B0 + BP * n;
const beatF = t => (t - B0) / BP;
function hash(a, b = 0) { const x = Math.sin(a * 12.9898 + b * 78.233 + 0.123) * 43758.5453; return x - Math.floor(x); }
function rng(seed) { let s = (Math.floor(seed * 2654435761) >>> 0) || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; }
function mk(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
const slamS = u => u < 0 ? 0 : 1 + 0.45 * Math.exp(-u * 16);
const kick = t => { const f = beatF(t); return Math.exp(-(f - Math.floor(f)) * 5.5); };

let AUD = null, FR = 0;
const A = (k) => (AUD && AUD[k] && AUD[k][Math.min(FR, AUD[k].length - 1)]) || 0;

// ---------- text ----------
function T(g, s, x, y, o = {}) {
  const { f = 'Anton', w = '', sz = 120, c = COL.cream, al = 'left', bl = 'alphabetic', ls = 0, sc = 1, rot = 0, a = 1, stroke = null, lw = 0, shadow = null, maxW = 0 } = o;
  g.save(); g.globalAlpha *= a; g.translate(x, y); if (rot) g.rotate(rot);
  g.font = `${w} ${sz}px "${f}"`; g.textAlign = al; g.textBaseline = bl; g.letterSpacing = ls + 'px';
  let s2 = sc;
  if (maxW) { const mw = g.measureText(s).width; if (mw > maxW) s2 *= maxW / mw; }
  if (s2 !== 1) g.scale(s2, s2);
  if (shadow) { g.shadowColor = shadow.c; g.shadowBlur = shadow.b; g.shadowOffsetX = shadow.x || 0; g.shadowOffsetY = shadow.y || 0; }
  if (stroke) { g.strokeStyle = stroke; g.lineWidth = lw; g.lineJoin = 'round'; g.strokeText(s, 0, 0); }
  if (c) { g.fillStyle = c; g.fillText(s, 0, 0); }
  g.restore();
}
function TW(g, s, f, sz, ls = 0, w = '') { g.save(); g.font = `${w} ${sz}px "${f}"`; g.letterSpacing = ls + 'px'; const m = g.measureText(s).width; g.restore(); return m; }
// slam word: scale-in punch with chromatic ghosts
function slam(g, s, x, y, u, o = {}) {
  if (u < 0) return;
  const sc = slamS(u) * (o.sc || 1);
  if (u < 0.1) {
    const k = (0.1 - u) / 0.1 * 18;
    T(g, s, x - k, y, { ...o, sc, c: COL.blue, a: 0.55 });
    T(g, s, x + k, y, { ...o, sc, c: COL.red, a: 0.55 });
  }
  T(g, s, x, y, { ...o, sc });
}
function typed(s, t0, t, cps = 28) { if (t < t0) return ''; return s.slice(0, Math.floor((t - t0) * cps)); }

// ---------- prerendered textures ----------
const TEX = {};
function buildTextures(img) {
  // grain tiles
  TEX.grain = [0, 1, 2].map(k => {
    const c = mk(256, 256), g = c.getContext('2d'), d = g.createImageData(256, 256), r = rng(100 + k);
    for (let i = 0; i < d.data.length; i += 4) { const v = r() * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
    g.putImageData(d, 0, 0); return c;
  });
  // grunge (alpha speckle for stamps)
  {
    const c = mk(512, 512), g = c.getContext('2d'), r = rng(7);
    for (let i = 0; i < 2600; i++) { g.fillStyle = `rgba(0,0,0,${0.3 + r() * 0.7})`; g.beginPath(); g.arc(r() * 512, r() * 512, r() * r() * 5 + 0.4, 0, 7); g.fill(); }
    for (let i = 0; i < 26; i++) { g.fillStyle = `rgba(0,0,0,${0.15 + r() * .3})`; g.beginPath(); g.ellipse(r() * 512, r() * 512, 8 + r() * 30, 2 + r() * 8, r() * 3, 0, 7); g.fill(); }
    TEX.grunge = ctx.createPattern(c, 'repeat');
  }
  // scanlines
  { const c = mk(4, 4), g = c.getContext('2d'); g.fillStyle = 'rgba(0,0,0,0.5)'; g.fillRect(0, 0, 4, 1); TEX.scan = ctx.createPattern(c, 'repeat'); }
  // vignette
  { const c = mk(W, H), g = c.getContext('2d'); const gr = g.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 1.05); gr.addColorStop(0, 'rgba(0,0,0,0)'); gr.addColorStop(1, 'rgba(0,0,0,0.75)'); g.fillStyle = gr; g.fillRect(0, 0, W, H); TEX.vig = c; }
  // halftone dot pattern
  { const c = mk(24, 24), g = c.getContext('2d'); g.fillStyle = 'rgba(0,0,0,0.22)'; g.beginPath(); g.arc(6, 6, 4, 0, 7); g.arc(18, 18, 4, 0, 7); g.fill(); TEX.dots = ctx.createPattern(c, 'repeat'); }
  // brick wall
  {
    const c = mk(W, H), g = c.getContext('2d'), r = rng(11);
    g.fillStyle = '#0d0b0b'; g.fillRect(0, 0, W, H);
    const bw = 128, bh = 46, m = 6;
    for (let row = 0, y = 0; y < H; row++, y += bh + m) {
      for (let x = -(row % 2) * bw / 2; x < W; x += bw + m) {
        const l = 9 + r() * 8, s = 18 + r() * 14;
        g.fillStyle = `hsl(${8 + r() * 14},${s}%,${l}%)`; g.fillRect(x, y, bw, bh);
        g.fillStyle = `rgba(255,255,255,${r() * 0.04})`; g.fillRect(x, y, bw, 3);
        g.fillStyle = `rgba(0,0,0,${0.2 + r() * 0.2})`; g.fillRect(x, y + bh - 5, bw, 5);
      }
    }
    for (let i = 0; i < 1800; i++) { g.fillStyle = `rgba(0,0,0,${r() * 0.5})`; g.fillRect(r() * W, r() * H, 1 + r() * 3, 1 + r() * 3); }
    for (let i = 0; i < 30; i++) { const x = r() * W, y = r() * H, rr = 80 + r() * 320; const gr = g.createRadialGradient(x, y, 0, x, y, rr); gr.addColorStop(0, `rgba(0,0,0,${0.3 + r() * 0.4})`); gr.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = gr; g.fillRect(x - rr, y - rr, rr * 2, rr * 2); }
    // drips of grime
    for (let i = 0; i < 40; i++) { const x = r() * W; g.fillStyle = `rgba(0,0,0,${0.15 + r() * .25})`; g.fillRect(x, 0, 2 + r() * 6, r() * H * 0.6); }
    g.fillStyle = 'rgba(0,0,0,0.35)'; g.fillRect(0, 0, W, H);
    TEX.brick = c;
  }
  // concrete
  {
    const c = mk(W, H), g = c.getContext('2d'), r = rng(23);
    g.fillStyle = '#141416'; g.fillRect(0, 0, W, H);
    for (let i = 0; i < 60; i++) { const x = r() * W, y = r() * H, rr = 60 + r() * 400; const gr = g.createRadialGradient(x, y, 0, x, y, rr); const v = r() < .5 ? '255,255,255' : '0,0,0'; gr.addColorStop(0, `rgba(${v},${0.03 + r() * 0.05})`); gr.addColorStop(1, `rgba(${v},0)`); g.fillStyle = gr; g.fillRect(x - rr, y - rr, rr * 2, rr * 2); }
    for (let i = 0; i < 9000; i++) { g.fillStyle = r() < .5 ? `rgba(255,255,255,${r() * .08})` : `rgba(0,0,0,${r() * .5})`; g.fillRect(r() * W, r() * H, 1 + r() * 2, 1 + r() * 2); }
    g.strokeStyle = 'rgba(0,0,0,0.6)'; g.lineWidth = 1.5;
    for (let k = 0; k < 7; k++) { let x = r() * W, y = r() * H; g.beginPath(); g.moveTo(x, y); for (let i = 0; i < 40; i++) { x += (r() - .5) * 40; y += (r() - .3) * 30; g.lineTo(x, y); } g.stroke(); }
    // expansion joints
    g.fillStyle = 'rgba(0,0,0,.45)'; g.fillRect(0, H * 0.62, W, 3); g.fillRect(W * 0.38, 0, 3, H);
    TEX.concrete = c;
  }
  // skyline silhouette + windows
  {
    const c = mk(W, 560), g = c.getContext('2d'), r = rng(31);
    TEX.windows = [];
    for (let layer = 0; layer < 2; layer++) {
      let x = -20;
      while (x < W) {
        const bw = 70 + r() * 160, bh = (layer ? 160 : 240) + r() * (layer ? 220 : 300);
        const y = 560 - bh;
        g.fillStyle = layer ? '#050506' : '#0f0f12'; g.fillRect(x, y, bw, bh);
        if (r() < .3) { g.fillRect(x + bw * .4, y - 40 - r() * 60, 4, 100); }
        if (layer) for (let wy = y + 18; wy < 540; wy += 22) for (let wx = x + 10; wx < x + bw - 14; wx += 18) if (r() < .45) TEX.windows.push([wx, wy, r()]);
        x += bw + (layer ? 4 : -30) + r() * 10;
      }
    }
    TEX.sky = c;
  }
  // hero crop treatments
  {
    const sw = 900, sh = 506, sx = 700, sy = 30;
    const base = mk(W, H), g = base.getContext('2d');
    g.drawImage(img.hero, sx, sy, sw, sh, 0, 0, W, H);
    TEX.heroRaw = base;
    const d = g.getImageData(0, 0, W, H), duo = mk(W, H), dg = duo.getContext('2d'), dd = dg.createImageData(W, H);
    const cre = mk(W, H), cg = cre.getContext('2d'), cd = cg.createImageData(W, H);
    for (let i = 0; i < d.data.length; i += 4) {
      let l = (d.data[i] * .3 + d.data[i + 1] * .59 + d.data[i + 2] * .11) / 255;
      l = clamp((l - 0.12) / 0.62); l = l * l * (3 - 2 * l);
      dd.data[i] = 10 + l * (244 - 10); dd.data[i + 1] = 10 + l * (197 - 10); dd.data[i + 2] = 11 + l * (66 - 11); dd.data[i + 3] = 255;
      cd.data[i] = 10 + l * 226; cd.data[i + 1] = 10 + l * 218; cd.data[i + 2] = 11 + l * 201; cd.data[i + 3] = 255;
    }
    dg.putImageData(dd, 0, 0); cg.putImageData(cd, 0, 0);
    TEX.heroDuo = duo; TEX.heroCream = cre;
    // halftone
    const small = mk(160, 90), sg = small.getContext('2d'); sg.drawImage(base, 0, 0, 160, 90);
    const sd = sg.getImageData(0, 0, 160, 90).data;
    const ht = mk(W, H), hg = ht.getContext('2d'); hg.fillStyle = COL.blk; hg.fillRect(0, 0, W, H); hg.fillStyle = COL.y;
    for (let yy = 0; yy < 90; yy++) for (let xx = 0; xx < 160; xx++) {
      const k = (yy * 160 + xx) * 4; let l = (sd[k] * .3 + sd[k + 1] * .59 + sd[k + 2] * .11) / 255; l = clamp((l - .08) / .7);
      const rr = 6.4 * Math.sqrt(l); if (rr < .5) continue; hg.beginPath(); hg.arc(xx * 12 + 6, yy * 12 + 6, rr, 0, 7); hg.fill();
    }
    TEX.heroHT = ht;
  }
  TEX.stamp = mk(1700, 520);
  TEX.feed = mk(760, H);
  TEX.R = mk(W, H); TEX.G = mk(W, H); TEX.B = mk(W, H);
  TEX.S = mk(W, H);
  TEX.tmp = mk(W, H);
}

// ---------- graphic helpers ----------
function bg(g, tex, a = 1, dx = 0, dy = 0, sc = 1) {
  g.save(); g.globalAlpha = a; g.translate(W / 2 + dx, H / 2 + dy); g.scale(sc, sc); g.drawImage(tex, -W / 2, -H / 2); g.restore();
}
function fill(g, c, a = 1) { g.save(); g.globalAlpha = a; g.fillStyle = c; g.fillRect(0, 0, W, H); g.restore(); }

function tornPath(g, w, h, seed, j = 7) {
  const r = rng(seed), st = 16; g.beginPath(); g.moveTo(0, r() * j);
  for (let x = st; x < w; x += st) g.lineTo(x, (r() - .3) * j); g.lineTo(w, r() * j);
  for (let y = st; y < h; y += st) g.lineTo(w - (r() - .3) * j, y); g.lineTo(w - r() * j, h);
  for (let x = w - st; x > 0; x -= st) g.lineTo(x, h - (r() - .3) * j); g.lineTo(r() * j, h);
  for (let y = h - st; y > 0; y -= st) g.lineTo((r() - .3) * j, y); g.closePath();
}
function poster(g, cx, cy, w, h, rot, seed, paper, draw, sc = 1) {
  g.save(); g.translate(cx, cy); g.rotate(rot); g.scale(sc, sc); g.translate(-w / 2, -h / 2);
  g.save(); g.translate(12, 16); tornPath(g, w, h, seed); g.fillStyle = 'rgba(0,0,0,.5)'; g.fill(); g.restore();
  tornPath(g, w, h, seed); g.fillStyle = paper; g.fill();
  g.save(); g.clip(); draw(g, w, h);
  const r = rng(seed + 9); g.globalAlpha = .07; g.strokeStyle = '#000';
  for (let i = 0; i < 6; i++) { g.beginPath(); g.moveTo(r() * w, 0); g.lineTo(r() * w, h); g.lineWidth = 1 + r() * 4; g.stroke(); }
  g.globalAlpha = .5; g.fillStyle = TEX.grunge; g.globalCompositeOperation = 'multiply'; g.fillRect(0, 0, w, h);
  g.restore(); g.restore();
}
function tape(g, cx, cy, ang, len, th, off, label, p = 1, o = {}) {
  g.save(); g.translate(cx, cy); g.rotate(ang);
  g.beginPath(); g.rect(-len / 2, -th / 2 - 30, len * clamp(p), th + 60); g.clip();
  g.fillStyle = 'rgba(0,0,0,.45)'; g.fillRect(-len / 2 + 8, -th / 2 + 14, len, th);
  g.fillStyle = o.bg || COL.y; g.fillRect(-len / 2, -th / 2, len, th);
  g.beginPath(); g.rect(-len / 2, -th / 2, len, th); g.clip();
  const fg = o.fg || COL.blk;
  if (label) {
    g.fillStyle = fg; g.fillRect(-len / 2, -th / 2, len, th * 0.09); g.fillRect(-len / 2, th / 2 - th * 0.09, len, th * 0.09);
    g.font = `${th * 0.6}px "Anton"`; g.textBaseline = 'middle'; g.letterSpacing = (th * 0.04) + 'px'; g.textAlign = 'left';
    const unit = label + '   /   '; const uw = g.measureText(unit).width;
    let sx = -len / 2 - (((off % uw) + uw) % uw);
    g.fillStyle = fg; for (let x = sx; x < len / 2; x += uw) g.fillText(unit, x, th * 0.03);
  } else {
    const sw = th * 0.9; g.fillStyle = fg; let s0 = -len / 2 - (((off % (sw * 2)) + sw * 2) % (sw * 2)) - th;
    for (let x = s0; x < len / 2 + th; x += sw * 2) { g.beginPath(); g.moveTo(x, -th / 2); g.lineTo(x + sw, -th / 2); g.lineTo(x + sw + th, th / 2); g.lineTo(x + th, th / 2); g.closePath(); g.fill(); }
  }
  g.globalAlpha = .35; g.globalCompositeOperation = 'destination-out'; g.fillStyle = TEX.grunge; g.fillRect(-len / 2, -th / 2, len, th);
  g.restore();
}
function spray(g, s, x, y, sz, p, o = {}) {
  const c = o.c || COL.y; g.save(); g.translate(x, y); g.rotate(o.rot || 0);
  g.font = `${sz}px "Permanent Marker"`; g.textBaseline = 'alphabetic'; g.textAlign = 'left'; g.letterSpacing = '0px';
  const w = g.measureText(s).width; const ox = o.al === 'center' ? -w / 2 : (o.al === 'right' ? -w : 0);
  g.beginPath(); g.rect(ox - 30, -sz * 1.6, (w + 60) * clamp(p), sz * 4); g.clip();
  g.lineJoin = 'round';
  if (o.out !== null) { g.strokeStyle = o.out || COL.blk; g.lineWidth = sz * 0.13; g.strokeText(s, ox, 0); }
  g.shadowColor = c; g.shadowBlur = sz * 0.22; g.fillStyle = c; g.fillText(s, ox, 0); g.shadowBlur = 0; g.fillText(s, ox, 0);
  const r = rng(o.seed || 7), nd = o.drips ?? 7, dt = o.dt ?? 9;
  for (let i = 0; i < nd; i++) {
    const fx = r(), dx = ox + fx * w, L = sz * (0.35 + r() * 1.1), st = r() * 0.4;
    const q = eo((dt - st - fx * 0.4) / 1.8); if (q <= 0 || fx > p) continue;
    const ww = 3 + r() * sz * 0.045; g.fillStyle = c; g.fillRect(dx - ww / 2, -sz * 0.18, ww, L * q);
    g.beginPath(); g.arc(dx, -sz * 0.18 + L * q, ww * 0.8, 0, 7); g.fill();
  }
  g.restore();
}
function stamp(g, s, x, y, sz, rot, c, u, o = {}) {
  if (u < 0) return;
  const sc = TEX.stamp, sg = sc.getContext('2d'); sg.clearRect(0, 0, sc.width, sc.height);
  sg.font = `${sz}px "${o.f || 'Saira Stencil One'}"`; sg.letterSpacing = (o.ls ?? sz * 0.03) + 'px';
  const w = Math.min(1560, sg.measureText(s).width), pad = sz * 0.28, bw = w + pad * 2, bh = sz * 1.3;
  const x0 = (sc.width - bw) / 2, y0 = (sc.height - bh) / 2;
  sg.strokeStyle = c; sg.lineWidth = sz * 0.07; if (o.box !== false) sg.strokeRect(x0, y0, bw, bh);
  sg.fillStyle = c; sg.textAlign = 'center'; sg.textBaseline = 'middle'; sg.fillText(s, sc.width / 2, sc.height / 2 + sz * 0.04, 1560);
  sg.globalCompositeOperation = 'destination-out'; sg.save(); sg.translate(hash(s.length) * 400, 0); sg.fillStyle = TEX.grunge; sg.fillRect(-400, 0, sc.width + 400, sc.height); sg.restore(); sg.globalCompositeOperation = 'source-over';
  const k = 1 + 1.1 * Math.exp(-u * 22);
  g.save(); g.globalAlpha *= clamp(u * 25) * (o.a ?? 1); g.translate(x, y); g.rotate(rot); g.scale(k * (o.sc || 1), k * (o.sc || 1)); g.drawImage(sc, -sc.width / 2, -sc.height / 2); g.restore();
}
function barcode(g, x, y, w, h, seed) {
  const r = rng(seed); let xx = x; g.fillStyle = '#111';
  while (xx < x + w) { const bw = 2 + Math.floor(r() * 4) * 2; if (r() < .6) g.fillRect(xx, y, Math.min(bw, x + w - xx), h); xx += bw + 2; }
}
function label(g, cx, cy, rot, u, o = {}) {
  if (u < 0) return;
  const w = o.w || 520, h = o.h || 330, k = (o.sc || 1) * (1 + 0.5 * Math.exp(-u * 20));
  g.save(); g.translate(cx, cy); g.rotate(rot); g.scale(k, k); g.translate(-w / 2, -h / 2);
  g.fillStyle = 'rgba(0,0,0,.55)'; g.fillRect(10, 16, w, h);
  g.fillStyle = '#f2ede2'; g.fillRect(0, 0, w, h);
  g.strokeStyle = '#111'; g.lineWidth = 6; g.strokeRect(9, 9, w - 18, h - 18);
  g.fillStyle = '#111'; g.fillRect(9, 9, w - 18, 72);
  T(g, o.title || 'DELIVERY SHELF', 28, 66, { sz: 52, c: o.tc || COL.y, ls: 2, maxW: w - 150 });
  const rows = o.rows || ['FROM: HERMES AGENT', 'TO: YOUR SHELF', 'CONTENTS: FINISHED WORK'];
  rows.forEach((s, i) => T(g, s, 28, 122 + i * 36, { f: 'JetBrains Mono', w: 700, sz: 22, c: '#111' }));
  barcode(g, 28, h - 100, w - 200, 60, o.seed || 3);
  T(g, o.track || 'DS-0412-7781-KW', 28, h - 22, { f: 'JetBrains Mono', w: 700, sz: 18, c: '#111' });
  if (o.badge) { g.fillStyle = o.bc || COL.y; g.beginPath(); g.arc(w - 88, h - 92, 62, 0, 7); g.fill(); g.strokeStyle = '#111'; g.lineWidth = 5; g.stroke(); T(g, o.badge, w - 88, h - 70, { sz: 64, c: '#111', al: 'center' }); }
  g.globalAlpha = .25; g.globalCompositeOperation = 'multiply'; g.fillStyle = TEX.grunge; g.fillRect(0, 0, w, h);
  g.restore();
}
function sticker(g, cx, cy, rot, u, txt, o = {}) {
  if (u < 0) return;
  const k = (o.sc || 1) * (1 + 0.6 * Math.exp(-u * 22));
  g.save(); g.translate(cx, cy); g.rotate(rot); g.scale(k, k);
  g.font = `${o.sz || 70}px "${o.f || 'Anton'}"`; g.letterSpacing = '1px';
  const w = g.measureText(txt).width + 60, h = (o.sz || 70) * 1.35;
  g.fillStyle = 'rgba(0,0,0,.5)'; g.beginPath(); g.roundRect(-w / 2 + 8, -h / 2 + 12, w, h, 14); g.fill();
  g.fillStyle = '#fff'; g.beginPath(); g.roundRect(-w / 2 - 8, -h / 2 - 8, w + 16, h + 16, 20); g.fill();
  g.fillStyle = o.bg || COL.y; g.beginPath(); g.roundRect(-w / 2, -h / 2, w, h, 14); g.fill();
  g.fillStyle = o.fg || COL.blk; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(txt, 0, (o.sz || 70) * 0.06);
  g.restore();
}
function badge(g, x, y, r, letter, c, tc = COL.blk) {
  g.fillStyle = c; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill();
  T(g, letter, x, y + r * 0.02, { f: 'Inter', w: 800, sz: r * 1.25, c: tc, al: 'center', bl: 'middle' });
}
function neon(g, s, x, y, sz, c, on, o = {}) {
  g.save(); g.font = `${sz}px "${o.f || 'Permanent Marker'}"`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.lineJoin = 'round'; g.letterSpacing = (o.ls || 0) + 'px';
  if (o.rot) { g.translate(x, y); g.rotate(o.rot); x = 0; y = 0; }
  g.strokeStyle = 'rgba(80,70,60,0.5)'; g.lineWidth = sz * 0.06; g.strokeText(s, x, y);
  if (on > 0) {
    g.globalAlpha = on; g.strokeStyle = c; g.shadowColor = c; g.shadowBlur = sz * 0.6; g.lineWidth = sz * 0.07; g.strokeText(s, x, y);
    g.shadowBlur = sz * 0.18; g.strokeText(s, x, y); g.shadowBlur = 0; g.strokeStyle = '#fffbe9'; g.lineWidth = sz * 0.022; g.strokeText(s, x, y);
  }
  g.restore();
}
function rain(g, t, n = 260, a = 0.22) {
  g.save(); g.strokeStyle = `rgba(190,200,215,${a})`; g.lineWidth = 1.6; g.beginPath();
  for (let i = 0; i < n; i++) {
    const sp = 1500 * (0.7 + hash(i, 2) * 0.6), L = 26 + hash(i, 3) * 40;
    const y = ((hash(i, 1) * (H + 200) + t * sp) % (H + 200)) - 100; const x = hash(i) * (W + 300) - y * 0.14;
    g.moveTo(x, y); g.lineTo(x - L * 0.14, y + L);
  }
  g.stroke(); g.restore();
}
function hexStream(g, t, x, y, cols, rows, o = {}) {
  g.save(); g.font = `500 ${o.sz || 16}px "JetBrains Mono"`; g.fillStyle = o.c || 'rgba(244,197,66,0.22)'; g.textBaseline = 'top';
  const step = Math.floor(t * (o.rate || 12));
  for (let r = 0; r < rows; r++) {
    let line = ''; for (let k = 0; k < cols; k++) { const h = Math.floor(hash(r * 31 + k, step + r * 7) * 256); line += h.toString(16).padStart(2, '0') + ' '; }
    g.fillText(line, x, y + r * (o.lh || 22));
  }
  g.restore();
}
function skyline(g, t, y0, a = 1, beatLit = 0) {
  g.save(); g.globalAlpha = a; g.drawImage(TEX.sky, 0, y0);
  const b = Math.floor(beatF(t));
  g.fillStyle = COL.y;
  for (let i = 0; i < TEX.windows.length; i++) {
    const [wx, wy, r] = TEX.windows[i]; const on = hash(i, b * beatLit) < 0.38;
    if (!on) continue; g.globalAlpha = a * (0.25 + r * 0.6); g.fillRect(wx, y0 + wy, 9, 11);
  }
  g.restore();
}
// The Delivery Shelf mark, drawn from the brand geometry (1024 grid, centred).
function mark(g, cx, cy, s, p = {}) {
  const drop = u => (u === undefined ? 0 : (u < 0 ? -9999 : -(1 - eback(u / 0.35)) * 260));
  g.save(); g.translate(cx, cy); g.scale(s, s); g.translate(-512, -511);
  const cream = p.cream || COL.cream, yel = p.yel || COL.y;
  const dF = drop(p.frame), dD = drop(p.doc), dS = drop(p.shelf);
  if (dF > -9000) {
    g.save(); g.translate(0, dF); g.fillStyle = cream;
    g.beginPath(); g.rect(165, 409, 365, 255); g.rect(199, 442, 298, 186); g.fill('evenodd');
    g.beginPath(); g.moveTo(347, 483); g.lineTo(480, 628); g.lineTo(497, 628); g.lineTo(497, 664); g.lineTo(199, 664); g.lineTo(199, 628); g.lineTo(213, 628); g.closePath(); g.fill();
    g.restore();
  }
  if (dD > -9000) { g.save(); g.translate(0, dD); g.fillStyle = yel; g.beginPath(); g.moveTo(570, 297); g.lineTo(761, 297); g.lineTo(851, 388); g.lineTo(851, 664); g.lineTo(570, 664); g.closePath(); g.fill(); g.restore(); }
  if (dS > -9000) {
    g.save(); g.translate(0, -dS * 0.0 + (p.shelf === undefined ? 0 : (p.shelf < 0 ? 0 : (1 - eback(p.shelf / 0.3)) * 120))); g.globalAlpha *= p.shelf === undefined ? 1 : clamp(p.shelf * 8);
    g.fillStyle = cream; g.beginPath(); g.moveTo(103, 645); g.lineTo(133, 645); g.lineTo(133, 664); g.lineTo(891, 664); g.lineTo(891, 645); g.lineTo(921, 645); g.lineTo(921, 725); g.lineTo(103, 725); g.closePath(); g.fill();
    if (p.led !== false) { g.fillStyle = p.ledc || COL.blue; g.fillRect(823, 685, 54, 20); }
    g.restore();
  }
  g.restore();
}
function terminal(g, x, y, w, h, title, lines, t, o = {}) {
  const sz = o.sz || 34, lh = sz * 1.55;
  g.save();
  g.fillStyle = 'rgba(0,0,0,.55)'; g.fillRect(x + 14, y + 18, w, h);
  g.fillStyle = '#0c0c0e'; g.fillRect(x, y, w, h);
  g.strokeStyle = o.border || COL.y; g.lineWidth = 3; g.strokeRect(x, y, w, h);
  g.fillStyle = o.border || COL.y; g.fillRect(x, y, w, 46);
  T(g, title, x + 20, y + 32, { f: 'JetBrains Mono', w: 800, sz: 20, c: COL.blk, ls: 2 });
  T(g, '■ ■ ■', x + w - 20, y + 31, { f: 'JetBrains Mono', w: 800, sz: 16, c: COL.blk, al: 'right' });
  let yy = y + 46 + lh * 0.95;
  let lastEnd = 0, cursorX = x + 30, cursorY = yy;
  for (const L of lines) {
    if (t < L.at) break;
    const s = L.cps ? typed(L.s, L.at, t, L.cps) : L.s;
    const pre = L.pre ?? '';
    if (pre) T(g, pre, x + 30, yy, { f: 'JetBrains Mono', w: 700, sz, c: COL.y });
    const px = x + 30 + (pre ? TW(g, pre, 'JetBrains Mono', sz, 0, 700) : 0);
    T(g, s, px, yy, { f: 'JetBrains Mono', w: L.w || 500, sz, c: L.c || COL.cream });
    cursorX = px + TW(g, s, 'JetBrains Mono', sz, 0, L.w || 500) + 6; cursorY = yy; yy += lh;
  }
  if (Math.floor(t * 2.4) % 2 === 0) { g.fillStyle = COL.y; g.fillRect(cursorX, cursorY - sz * 0.8, sz * 0.55, sz * 0.95); }
  g.restore();
}
function fileIcon(g, x, y, s, c, kind, o = {}) {
  g.save(); g.translate(x, y); g.scale(s, s);
  g.fillStyle = 'rgba(0,0,0,.45)'; g.beginPath(); g.moveTo(8, 12); g.lineTo(138, 12); g.lineTo(178, 52); g.lineTo(178, 232); g.lineTo(8, 232); g.fill();
  g.fillStyle = c; g.beginPath(); g.moveTo(0, 0); g.lineTo(130, 0); g.lineTo(170, 40); g.lineTo(170, 220); g.lineTo(0, 220); g.closePath(); g.fill();
  g.fillStyle = 'rgba(0,0,0,.25)'; g.beginPath(); g.moveTo(130, 0); g.lineTo(130, 40); g.lineTo(170, 40); g.fill();
  g.fillStyle = 'rgba(0,0,0,.2)'; for (let i = 0; i < 5; i++) g.fillRect(22, 80 + i * 22, 100 + (i % 2) * 26, 9);
  T(g, kind, 22, 62, { f: 'Anton', sz: 40, c: o.kc || COL.blk });
  g.restore();
}
function hudCorners(g, a = 1) {
  g.save(); g.globalAlpha = a; g.strokeStyle = COL.cream; g.lineWidth = 3; const m = 40, L = 46;
  for (const [x, y, sx, sy] of [[m, m, 1, 1], [W - m, m, -1, 1], [m, H - m, 1, -1], [W - m, H - m, -1, -1]]) { g.beginPath(); g.moveTo(x, y + sy * L); g.lineTo(x, y); g.lineTo(x + sx * L, y); g.stroke(); }
  g.restore();
}
function hud(g, t, a = 1, bottom = true) {
  if (a <= 0) return;
  g.save(); g.globalAlpha = a;
  hudCorners(g, 0.7);
  T(g, 'DELIVERY SHELF // PLUGIN FOR HERMES AGENT', 64, 82, { f: 'JetBrains Mono', w: 700, sz: 17, c: COL.cream, ls: 2, a: .85 });
  const tc = `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(Math.floor(t % 60)).padStart(2, '0')}:${String(FR % 30).padStart(2, '0')}`;
  if (Math.floor(t * 2) % 2 === 0) { g.fillStyle = COL.red; g.beginPath(); g.arc(W - 262, 76, 8, 0, 7); g.fill(); }
  T(g, 'REC  ' + tc, W - 64, 82, { f: 'JetBrains Mono', w: 700, sz: 17, c: COL.cream, al: 'right', ls: 2, a: .85 });
  if (!bottom) { g.restore(); return; }
  // audio meter
  const lo = A('low'), md = A('rms'), hi = A('high');
  for (let i = 0; i < 28; i++) {
    const m = i < 9 ? lo : i < 19 ? md : hi; const v = clamp(m * (0.55 + 0.6 * hash(i, FR)), 0, 1.2);
    g.fillStyle = i > 22 ? COL.red : i > 15 ? COL.y : COL.cream; g.globalAlpha = a * 0.8;
    const bh = 4 + v * 34; g.fillRect(64 + i * 9, H - 64 - bh, 6, bh);
  }
  g.globalAlpha = a;
  T(g, 'SIG LOCKED · 100 BPM', W - 64, H - 64, { f: 'JetBrains Mono', w: 700, sz: 17, c: COL.cream, al: 'right', ls: 2, a: .85 });
  g.restore();
}
function cover(g, img, x, y, w, h, a = 1) { // draw image covering rect
  const s = Math.max(w / img.width, h / img.height), iw = img.width * s, ih = img.height * s;
  g.save(); g.globalAlpha *= a; g.beginPath(); g.rect(x, y, w, h); g.clip(); g.drawImage(img, x + (w - iw) / 2, y + (h - ih) / 2, iw, ih); g.restore();
}

// ---------- chat feed ----------
const FILES = [['q3-report.pdf', 'PDF', '2.1 MB'], ['revenue-chart.png', 'PNG', '640 KB'], ['launch-deck.pptx', 'PPT', '8.4 MB'], ['pricing-model.xlsx', 'XLS', '312 KB'], ['cover.png', 'PNG', '1.2 MB'], ['launch-plan.pdf', 'PDF', '184 KB'], ['notes-final.md', 'MD', '9 KB'], ['report_final_v2.pdf', 'PDF', '2.3 MB'], ['report_final_v3_REAL.pdf', 'PDF', '2.3 MB'], ['summary.docx', 'DOC', '88 KB'], ['dataset.csv', 'CSV', '4.7 MB'], ['hero-render.png', 'PNG', '3.3 MB'], ['roadmap.pdf', 'PDF', '560 KB'], ['brand-board.png', 'PNG', '2.0 MB']];
const TYPECOL = { PDF: '#e5412d', PNG: '#2f6bff', PPT: '#f08a24', XLS: '#2fae6a', MD: '#8a8a8a', DOC: '#2f6bff', CSV: '#2fae6a' };
const FEED = (() => {
  const r = rng(42), out = []; let y = 110;
  for (let i = 0; i < 90; i++) {
    const user = i % 3 === 0; const m = { user, y, lines: 1 + Math.floor(r() * (user ? 2 : 3)), w: user ? 280 + r() * 220 : 470 + r() * 190, files: [], lw: [] };
    for (let k = 0; k < 4; k++) m.lw.push(0.45 + r() * 0.5);
    if (!user && r() < .8) { const n = r() < .35 ? 2 : 1; for (let k = 0; k < n; k++) m.files.push(FILES[Math.floor(r() * FILES.length)]); }
    m.h = 34 + m.lines * 24 + m.files.length * 80; y += m.h + 24; out.push(m);
  }
  return out;
})();
function drawFeed(g, P, w, h) {
  g.clearRect(0, 0, w, h);
  g.fillStyle = 'rgba(14,14,17,0.94)'; g.fillRect(0, 0, w, h);
  for (const m of FEED) {
    const y = m.y - P; if (y > h || y + m.h < 0) continue;
    const bw = m.w, x = m.user ? w - 28 - bw : 28;
    g.fillStyle = m.user ? '#20366f' : '#1e1e23'; g.beginPath(); g.roundRect(x, y, bw, m.h, 18); g.fill();
    for (let k = 0; k < m.lines; k++) { g.fillStyle = m.user ? 'rgba(220,230,255,.35)' : 'rgba(236,228,212,.28)'; g.beginPath(); g.roundRect(x + 22, y + 20 + k * 24, (bw - 44) * m.lw[k], 11, 5); g.fill(); }
    let fy = y + 26 + m.lines * 24;
    for (const [name, kind, size] of m.files) {
      g.fillStyle = '#2a2a31'; g.beginPath(); g.roundRect(x + 16, fy, bw - 32, 66, 12); g.fill();
      g.fillStyle = TYPECOL[kind]; g.beginPath(); g.roundRect(x + 28, fy + 10, 46, 46, 8); g.fill();
      T(g, kind, x + 51, fy + 41, { f: 'Inter', w: 800, sz: 15, c: '#fff', al: 'center' });
      T(g, name, x + 88, fy + 32, { f: 'Inter', w: 600, sz: 21, c: COL.cream, maxW: bw - 140 });
      T(g, size, x + 88, fy + 55, { f: 'JetBrains Mono', w: 500, sz: 15, c: COL.dim });
      fy += 80;
    }
  }
  g.fillStyle = '#0c0c0e'; g.fillRect(0, 0, w, 66); g.fillStyle = COL.y; g.fillRect(0, 64, w, 3);
  g.fillStyle = '#3ad07a'; g.beginPath(); g.arc(30, 33, 7, 0, 7); g.fill();
  T(g, 'HERMES · SESSION 0412 · LIVE', 50, 40, { f: 'JetBrains Mono', w: 700, sz: 18, c: COL.cream, ls: 2 });
}

// =====================================================================
// SCENES — each draws to g (scene canvas) and returns fx
// =====================================================================

// S1 cold open: 0 – b6
function s1(g, t) {
  fill(g, COL.blk);
  const fx = { hud: 0, glitch: 0, split: 0 };
  if (t < 0.09) return fx;
  if (t < 1.5) {
    const u = t - 0.09;
    const z = 1.12 - u * 0.06;
    bg(g, TEX.heroDuo, clamp(1 - (u - 1.0) * 2.5), Math.sin(u * 30) * 6 * Math.exp(-u * 3), 0, z);
    g.fillStyle = TEX.dots; g.globalAlpha = .7; g.fillRect(0, 0, W, H); g.globalAlpha = 1;
    hexStream(g, t, 70, 140, 12, 30, { c: 'rgba(10,10,11,0.55)', sz: 18, lh: 28 });
    stamp(g, 'INCOMING DELIVERY', 700, 870, 120, -0.03, COL.blk, u - 0.05, { box: true, a: clamp(1 - (u - 1.0) * 2.5) });
    fx.glitch = 0.9 * Math.exp(-u * 2.2) + (hash(FR) < 0.15 ? 0.6 : 0); fx.split = 14 * Math.exp(-u * 3); fx.flash = { c: '#fff', a: Math.exp(-u * 9) };
    return fx;
  }
  // silence: terminal whisper
  const u = t - 1.5;
  hexStream(g, t, 70, 120, 34, 38, { c: 'rgba(244,197,66,0.07)', sz: 16, lh: 24 });
  const l1 = typed('> hermes: task complete.', 1.55, t, 30);
  const l2 = typed('> 3 files delivered to chat_', 2.45, t, 30);
  T(g, l1, 330, 500, { f: 'JetBrains Mono', w: 700, sz: 52, c: COL.cream });
  T(g, l2, 330, 580, { f: 'JetBrains Mono', w: 700, sz: 52, c: COL.y });
  if (Math.floor(t * 4) % 2 === 0) { g.fillStyle = COL.y; g.fillRect(330 + TW(g, (t > 2.45 ? l2 : l1), 'JetBrains Mono', 52, 0, 700) + 8, (t > 2.45 ? 580 : 500) - 44, 28, 52); }
  fx.hud = clamp(u * 3);
  const pre = clamp((t - 3.1) / 0.6);
  fx.glitch = pre * 0.7; fx.split = pre * 10; fx.zoom = 1 + ei(pre) * 0.35;
  return fx;
}

// S2 problem: b6 – b24
function s2(g, t) {
  const lt = t - bt(6);
  bg(g, TEX.brick, 1, 0, 0, 1.05 + lt * 0.004);
  // chat feed
  const k = 0.45, a0 = 52; const P = a0 * (Math.exp(k * lt) - 1); const v = a0 * k * Math.exp(k * lt);
  const fw = 760; drawFeed(TEX.feed.getContext('2d'), P, fw, H);
  const fxp = 1080;
  g.save(); g.translate(fxp, 0);
  g.fillStyle = 'rgba(0,0,0,.5)'; g.fillRect(16, 0, fw, H);
  const n = v > 500 ? Math.min(7, Math.floor(v / 400)) : 1;
  if (n > 1) { for (let i = 0; i < n; i++) { g.globalAlpha = 1 / n * 1.6; g.drawImage(TEX.feed, 0, -i * v / FPS / n * 1.8); } g.globalAlpha = 1; }
  else g.drawImage(TEX.feed, 0, 0);
  g.fillStyle = COL.y; g.fillRect(-4, 0, 6, H);
  g.restore();
  // words
  const b = beatF(t), X = 110, MW = 900;
  const lines = [];
  const add = (bb, s, c, sz) => { if (b >= bb) lines.push({ u: t - bt(bb), s, c, sz }); };
  let card = null;
  if (b < 8) { add(6, 'YOUR AGENT', COL.cream, 170); add(7, 'SHIPS.', COL.y, 330); card = 0; }
  else if (b < 12) { const words = ['REPORTS.', 'DECKS.', 'CHARTS.', 'CODE.']; const i = Math.min(3, Math.floor(b - 8)); card = 1;
    const u = t - bt(8 + i);
    if (i % 2 === 1) { g.fillStyle = COL.y; const ww = TW(g, words[i], 'Anton', 300) + 60; g.save(); g.translate(X - 30, 330); g.scale(slamS(u), slamS(u)); g.fillRect(0, 0, ww, 330); g.restore(); }
    slam(g, words[i], X, 610, u, { sz: 300, c: i % 2 ? COL.blk : COL.cream, maxW: MW });
    T(g, `FILE 0${i + 1} / 04 · DELIVERED`, X, 300, { f: 'JetBrains Mono', w: 700, sz: 26, c: COL.y, ls: 4 });
  }
  else if (b < 16) { add(12, 'IT ALL', COL.cream, 190); add(13, 'LANDS IN', COL.cream, 190); add(14, 'THE CHAT.', COL.y, 250); }
  else if (b < 20) { add(16, 'THEN THE', COL.cream, 180); add(17, 'SCROLL', COL.y, 250); add(18, 'EATS IT.', COL.red, 250); }
  if (lines.length) {
    let y = b < 8 ? 380 : 330;
    for (const L of lines) { y += L.sz * 0.98; slam(g, L.s, X, y, L.u, { sz: L.sz, c: L.c, maxW: MW }); }
  }
  // red X over feed
  if (b >= 18 && b < 20) {
    const u = t - bt(18);
    g.save(); g.strokeStyle = COL.red; g.lineCap = 'round'; g.lineWidth = 46; g.shadowColor = COL.red; g.shadowBlur = 20;
    const p1 = eo(u / 0.25), p2 = eo((u - 0.3) / 0.25);
    g.beginPath(); g.moveTo(1180, 200); g.lineTo(1180 + 560 * p1, 200 + 640 * p1); g.stroke();
    if (p2 > 0) { g.beginPath(); g.moveTo(1740, 210); g.lineTo(1740 - 560 * p2, 210 + 640 * p2); g.stroke(); }
    g.restore();
  }
  const fx = { hud: 1, shake: 0.4, split: 2 + A('low') * 3 };
  if (b >= 20) {
    const u = t - bt(20);
    fill(g, COL.blk, clamp(u * 3) * 0.55);
    spray(g, "WHERE'D", 960, 470, 230, eo(u / 0.5), { al: 'center', c: COL.y, rot: -0.06, seed: 3, dt: u, drips: 9 });
    spray(g, 'IT GO?', 960, 760, 260, eo((u - 0.45) / 0.5), { al: 'center', c: COL.y, rot: -0.04, seed: 5, dt: u - 0.45, drips: 8 });
    if (b >= 22) {
      const u2 = t - bt(22);
      stamp(g, 'LOST IN THE FEED', 960, 930, 96, 0.02, COL.red, u2, {});
      fx.glitch = 0.25 + clamp(u2 / 1.2) * 0.9; fx.split = 6 + u2 * 14;
    }
  }
  if (b >= 14 && b < 16) fx.glitch = 0.15 * kick(t);
  return fx;
}

// S3 reveal: b24 – b48
function s3(g, t) {
  const b = beatF(t); const fx = { hud: 1, split: 2 };
  if (b < 26) { // caution tape slash
    const u = t - bt(24);
    fill(g, u < 0.08 ? COL.y : COL.blk);
    bg(g, TEX.concrete, u < 0.08 ? 0 : 1);
    tape(g, W / 2, H / 2 - 120, -0.22, 2600, 150, t * 600, 'DELIVERY SHELF', eo(u / 0.35));
    tape(g, W / 2, H / 2 + 160, 0.16, 2600, 120, -t * 500, null, eo((u - 0.15) / 0.35));
    tape(g, W / 2, H / 2 + 20, 0.03, 2600, 130, t * 420, 'KEEP THE WORK', eo((u - 0.6) / 0.3), { bg: COL.blk, fg: COL.y });
    fx.shake = 1; fx.flash = { c: COL.y, a: Math.exp(-u * 12) * 0.8 };
    return fx;
  }
  if (b < 32) { // logo build
    const u = t - bt(26);
    fill(g, COL.blk); bg(g, TEX.heroHT, 0.22, -40 + u * 10, 0, 1.08);
    bg(g, TEX.concrete, 0.35);
    hexStream(g, t, 1450, 140, 6, 34, { c: 'rgba(236,228,212,0.08)' });
    const cx = 560, cy = 560;
    mark(g, cx, cy, 0.62, { shelf: t - bt(26), frame: t - bt(27), doc: t - bt(28), led: b >= 29 ? true : false, ledc: (b >= 29 && Math.floor(t * 6) % 2) ? COL.blue : '#9db8ff' });
    if (b >= 30) { slam(g, 'DELIVERY', 1010, 470, t - bt(30), { sz: 150, c: COL.cream, ls: 6 }); }
    if (b >= 31) { slam(g, 'SHELF', 1000, 760, t - bt(31), { sz: 330, c: COL.y }); }
    if (b >= 31) T(g, typed('A PLUGIN FOR HERMES AGENT', bt(31) + 0.2, t, 40), 1012, 840, { f: 'JetBrains Mono', w: 700, sz: 30, c: COL.cream, ls: 6 });
    fx.shake = [26, 27, 28].some(n => t - bt(n) >= 0 && t - bt(n) < 0.15) ? 1.2 : 0.3;
    return fx;
  }
  if (b < 36) { // KEEP THE WORK / SKIP THE HUNT
    const u = t - bt(32);
    bg(g, TEX.brick, 1, -u * 8, 0, 1.06);
    poster(g, 600, 560, 980, 640, -0.035, 21, '#e9e1cf', (pg, w, h) => {
      pg.fillStyle = TEX.dots; pg.fillRect(0, 0, w, h);
      T(pg, 'KEEP', 50, 300, { f: 'Saira Stencil One', sz: 270, c: COL.blk });
      T(pg, 'THE WORK.', 50, 560, { f: 'Saira Stencil One', sz: 230, c: COL.blk, maxW: w - 100 });
    }, slamS(u) * 0.95);
    if (b >= 34) {
      const u2 = t - bt(34);
      spray(g, 'Skip the', 1180, 520, 170, eo(u2 / 0.35), { c: COL.y, rot: -0.08, seed: 9, dt: u2 });
      spray(g, 'HUNT.', 1150, 800, 300, eo((u2 - 0.3) / 0.4), { c: COL.y, rot: -0.07, seed: 12, dt: u2 - 0.3, drips: 9 });
    }
    fx.shake = 0.5;
    return fx;
  }
  if (b < 44) { // terminal /shelf add + shelf fill
    const u = t - bt(36);
    bg(g, TEX.concrete, 1, 0, 0, 1.02 + u * 0.004);
    hexStream(g, t, 60, 160, 10, 36, { c: 'rgba(236,228,212,0.06)' });
    const lines = [
      { at: bt(36) + 0.05, pre: '$ ', s: '/shelf add', cps: 18, c: COL.cream, w: 800 },
      { at: bt(38), s: '▸ latest delivery · 2 files', c: COL.dim },
      { at: bt(38) + 0.3, s: '  launch-plan.pdf   ✓ preserved', c: COL.cream },
      { at: bt(39), s: '  cover.png         ✓ preserved', c: COL.cream },
      { at: bt(40), s: '✓ SAVED · Northstar launch kit · v1', c: COL.y, w: 800 },
    ];
    poster(g, 560, 540, 940, 470, -0.02, 33, '#e9e1cf', (pg, w, h) => { terminal(pg, 22, 22, w - 44, h - 44, 'HERMES // CHAT', lines, t, { sz: 30 }); });
    // shelf on right
    const sx = 1500, sy = 760;
    g.fillStyle = COL.cream; g.fillRect(sx - 330, sy, 660, 40); g.fillRect(sx - 330, sy - 18, 22, 22); g.fillRect(sx + 308, sy - 18, 22, 22);
    g.fillStyle = COL.blue; g.fillRect(sx + 230, sy + 12, 40, 14);
    const fly = (u0, tx, c, kind) => { const q = t - u0; if (q < 0) return; const p = eback(q / 0.4); const x = lerp(-300, tx, p), y = lerp(200, sy - 220, p) - Math.sin(clamp(q / 0.4) * Math.PI) * 120; fileIcon(g, x, y, 1, c, kind); };
    fly(bt(38) + 0.3, sx - 250, COL.cream, 'PDF');
    fly(bt(39), sx + 20, COL.y, 'PNG');
    if (b >= 40) slam(g, 'ONE COMMAND.', 1180, 300, t - bt(40), { sz: 150, c: COL.cream, maxW: 680 });
    if (b >= 42) slam(g, 'SAVED TOGETHER.', 1180, 430, t - bt(42), { sz: 110, c: COL.y, maxW: 680 });
    fx.shake = 0.3;
    return fx;
  }
  // b44–48 preserved stamp + labels
  const u = t - bt(44);
  bg(g, TEX.brick, 1, 0, 0, 1.04 + u * 0.01);
  label(g, 640, 560, -0.08, t - bt(44), { title: 'DELIVERY SHELF', rows: ['FROM: HERMES AGENT', 'TO: YOUR SHELF', 'CONTENTS: LAUNCH KIT'], badge: 'v1', sc: 1.35, seed: 4 });
  label(g, 1330, 470, 0.07, t - bt(45), { title: 'PRESERVED COPY', rows: ['launch-plan.pdf', 'cover.png', 'KEPT TOGETHER'], badge: '2', sc: 1.1, seed: 8, track: 'DS-0412-7782-KW' });
  stamp(g, 'PRESERVED', 1060, 820, 150, -0.1, COL.red, t - bt(46), {});
  fx.shake = [44, 45, 46].some(n => t - bt(n) >= 0 && t - bt(n) < 0.12) ? 1.2 : 0.3;
  return fx;
}

// S4 breakdown: b48 – b60 (night street, neon, product)
function s4(g, t) {
  const lt = t - bt(48), b = beatF(t);
  bg(g, TEX.brick, 1, -lt * 6, 0, 1.08);
  fill(g, '#050510', 0.45);
  skyline(g, t, H - 420, 0.55, 0);
  const lib = b >= 56;
  const img = lib ? IMG.lib : IMG.tog;
  const u = lib ? t - bt(56) : lt;
  // billboard
  g.save();
  const sc = (lib ? 0.62 : 0.86) * (1 + u * 0.012);
  const iw = img.width * sc, ih = img.height * sc;
  const cx = lib ? 1250 : 1100, cy = 610;
  g.translate(cx, cy); g.transform(1, -0.035, 0.0, 1, 0, 0);
  g.fillStyle = 'rgba(0,0,0,.6)'; g.fillRect(-iw / 2 + 18, -ih / 2 + 24, iw, ih);
  g.shadowColor = COL.y; g.shadowBlur = 40 * (0.6 + 0.4 * Math.sin(t * 3)); g.fillStyle = COL.y; g.fillRect(-iw / 2 - 8, -ih / 2 - 8, iw + 16, ih + 16); g.shadowBlur = 0;
  g.drawImage(img, -iw / 2, -ih / 2, iw, ih);
  g.fillStyle = 'rgba(244,197,66,0.06)'; g.fillRect(-iw / 2, -ih / 2, iw, ih);
  g.restore();
  // neon sign
  const flick = (hash(Math.floor(t * 14), 5) < 0.1 ? 0.2 : 1) * clamp(u * 3);
  if (!lib) neon(g, 'Together.', 420, 200, 150, COL.y, flick, { rot: -0.05 });
  else { neon(g, 'Library.', 380, 210, 140, COL.y, b >= 56 ? flick : 0, { rot: -0.05 }); neon(g, 'Gallery.', 420, 380, 140, '#7aa6ff', b >= 58 ? (hash(Math.floor(t * 13), 9) < 0.12 ? 0.2 : 1) : 0, { rot: -0.05 }); }
  // callouts
  if (!lib) {
    const cs = [[50, '1 DELIVERY'], [52, '2 FILES'], [54, 'KEPT TOGETHER']];
    cs.forEach(([bb, s], i) => { if (b >= bb) sticker(g, 300 + i * 30, 470 + i * 140, -0.04 + i * 0.03, t - bt(bb), s, { sz: 60, bg: i === 2 ? COL.y : COL.cream }); });
  } else {
    if (b >= 57) sticker(g, 330, 600, -0.05, t - bt(57), 'ONE FILE LIST', { sz: 56, bg: COL.cream });
    if (b >= 59) sticker(g, 380, 740, 0.04, t - bt(59), 'THUMBNAILS', { sz: 56, bg: '#7aa6ff' });
  }
  // subway sign bar
  g.fillStyle = '#0b0b0c'; g.fillRect(0, H - 120, W, 120); g.fillStyle = COL.cream; g.fillRect(0, H - 120, W, 4);
  const views = [['T', 'TOGETHER', COL.y], ['L', 'LIBRARY', COL.cream], ['G', 'GALLERY', '#7aa6ff']];
  const cur = lib ? (b >= 58 ? 2 : 1) : 0;
  views.forEach(([l, s, c], i) => { const x = 120 + i * 470; g.globalAlpha = i === cur ? 1 : 0.35; badge(g, x, H - 60, 32, l, c); T(g, s, x + 52, H - 44, { f: 'Inter', w: 800, sz: 44, c: COL.cream, ls: 2 }); g.globalAlpha = 1; });
  T(g, 'SAVED → DELIVERABLES', W - 80, H - 46, { f: 'JetBrains Mono', w: 700, sz: 24, c: COL.dim, al: 'right', ls: 3 });
  rain(g, t, 240, 0.2);
  return { hud: 1, hudBottom: false, split: 1.5, shake: 0.1, flash: lib && u < 0.2 ? { c: '#fff', a: (0.2 - u) * 2 } : null };
}

// S5 features: b60 – b96
function s5(g, t) {
  const b = beatF(t); const fx = { hud: 1, split: 2 + A('low') * 3, shake: 0.4 };
  const on = (n) => t - bt(n);
  if (b < 64) { // versions
    fill(g, COL.y); g.fillStyle = TEX.dots; g.fillRect(0, 0, W, H);
    slam(g, 'VERSIONS.', 110, 380, on(60), { sz: 250, c: COL.blk });
    if (b >= 61) slam(g, 'NOT OVERWRITES.', 116, 520, on(61), { sz: 120, c: COL.blk, maxW: 860 });
    if (b >= 62) T(g, typed('Add version → earlier files stay available.', bt(62), t, 40), 120, 620, { f: 'JetBrains Mono', w: 700, sz: 28, c: COL.blk });
    label(g, 1450, 400, -0.12, on(61), { title: 'LAUNCH KIT', badge: 'v1', rows: ['launch-plan.pdf', 'cover.png', 'SAVED NOV 04'], seed: 21, bc: COL.cream });
    label(g, 1530, 560, 0.04, on(62), { title: 'LAUNCH KIT', badge: 'v2', rows: ['launch-plan.pdf', 'cover.png', 'SAVED NOV 08'], seed: 22, bc: '#7aa6ff' });
    label(g, 1590, 720, -0.05, on(63), { title: 'LAUNCH KIT', badge: 'v3', rows: ['launch-plan.pdf', 'cover.png', 'SAVED NOV 11'], seed: 23, tc: COL.y });
    return fx;
  }
  if (b < 68) { // archive trash recover
    bg(g, TEX.concrete);
    const ws = [['ARCHIVE.', COL.cream], ['TRASH.', COL.y], ['RECOVER.', '#7aa6ff']];
    ws.forEach(([s, c], i) => { if (b >= 64 + i) slam(g, s, 110, 340 + i * 220, on(64 + i), { f: 'Saira Stencil One', sz: 175, c }); });
    const rem = Math.max(0, 3600 - Math.max(0, on(66)) * 1100);
    const mm = String(Math.floor(rem / 60)).padStart(2, '0'), ss = String(Math.floor(rem % 60)).padStart(2, '0');
    g.fillStyle = '#0b0b0c'; g.fillRect(1300, 330, 540, 420); g.strokeStyle = COL.red; g.lineWidth = 4; g.strokeRect(1300, 330, 540, 420);
    T(g, 'PENDING DELETION', 1336, 400, { f: 'JetBrains Mono', w: 800, sz: 28, c: COL.red, ls: 4 });
    T(g, `${mm}:${ss}`, 1570, 620, { f: 'JetBrains Mono', w: 800, sz: 160, c: COL.cream, al: 'center', a: b >= 67 ? 0.18 : 1 });
    T(g, 'RECOVERY WINDOW', 1336, 715, { f: 'JetBrains Mono', w: 700, sz: 24, c: COL.dim, ls: 4 });
    if (b >= 67) stamp(g, 'RESTORED', 1570, 560, 74, -0.12, COL.y, on(67), {});
    T(g, 'Trash keeps deliveries recoverable for 30 or 60 days.', 110, 930, { f: 'JetBrains Mono', w: 700, sz: 26, c: COL.cream, a: b >= 65 ? 0.9 : 0 });
    return fx;
  }
  if (b < 72) { // originals never the target
    const u = on(68);
    bg(g, TEX.brick, 1, 0, 0, 1.04);
    slam(g, 'YOUR ORIGINALS', 110, 250, u, { sz: 150, c: COL.cream });
    if (b >= 70) slam(g, 'ARE NEVER THE TARGET.', 110, 390, on(70), { sz: 130, c: COL.y, maxW: 1700 });
    fileIcon(g, 430, 520, 1.6, COL.cream, 'ORIG');
    fileIcon(g, 1220, 520, 1.6, COL.y, 'COPY');
    T(g, 'YOUR WORKING FILE', 566, 940, { f: 'JetBrains Mono', w: 700, sz: 26, c: COL.cream, al: 'center', ls: 3 });
    T(g, 'SHELF-PRESERVED COPY', 1356, 940, { f: 'JetBrains Mono', w: 700, sz: 26, c: COL.y, al: 'center', ls: 3 });
    // reticle moves from original to copy
    const p = eio((u - 0.5) / 0.9);
    const rx = lerp(566, 1356, p), ry = 700 + Math.sin(p * Math.PI) * -60;
    g.save(); g.strokeStyle = COL.red; g.lineWidth = 6; g.shadowColor = COL.red; g.shadowBlur = 14;
    g.beginPath(); g.arc(rx, ry, 120, 0, 7); g.stroke(); g.beginPath(); g.arc(rx, ry, 18, 0, 7); g.stroke();
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) { g.beginPath(); g.moveTo(rx + dx * 80, ry + dy * 80); g.lineTo(rx + dx * 160, ry + dy * 160); g.stroke(); }
    g.restore();
    if (b >= 71) stamp(g, 'UNTOUCHED', 566, 700, 90, -0.15, COL.y, on(71), {});
    return fx;
  }
  if (b < 76) { // retrieve from chat
    fill(g, COL.blk); skyline(g, t, H - 520, 0.9, 1); fill(g, '#000', 0.25);
    slam(g, 'RETRIEVE', 110, 360, on(72), { sz: 230, c: COL.cream });
    if (b >= 73) slam(g, 'FROM CHAT.', 110, 580, on(73), { sz: 230, c: COL.y });
    if (b >= 75) T(g, 'Telegram file sending · no model call', 116, 670, { f: 'JetBrains Mono', w: 700, sz: 30, c: COL.cream });
    // phone
    const px = 1240, py = 120, pw = 470, ph = 860;
    g.fillStyle = 'rgba(0,0,0,.6)'; g.beginPath(); g.roundRect(px + 18, py + 24, pw, ph, 54); g.fill();
    g.fillStyle = '#16161a'; g.beginPath(); g.roundRect(px, py, pw, ph, 54); g.fill(); g.strokeStyle = COL.cream; g.lineWidth = 5; g.stroke();
    g.fillStyle = '#0d0d10'; g.beginPath(); g.roundRect(px + 18, py + 18, pw - 36, ph - 36, 40); g.fill();
    T(g, 'HERMES BOT', px + pw / 2, py + 80, { f: 'Inter', w: 800, sz: 26, c: COL.cream, al: 'center', ls: 2 });
    g.fillStyle = 'rgba(236,228,212,.15)'; g.fillRect(px + 18, py + 104, pw - 36, 2);
    const cmd = typed('/shelf r3', bt(72) + 0.1, t, 16);
    if (cmd) { const bw = 40 + TW(g, cmd, 'JetBrains Mono', 34, 0, 700); g.fillStyle = '#20366f'; g.beginPath(); g.roundRect(px + pw - 40 - bw, py + 160, bw, 70, 22); g.fill(); T(g, cmd, px + pw - 40 - bw + 20, py + 207, { f: 'JetBrains Mono', w: 700, sz: 34, c: '#fff' }); }
    if (b >= 74) {
      const q = eback(on(74) / 0.35);
      g.save(); g.translate(px + 40, py + 270 + (1 - q) * 40); g.globalAlpha = clamp(on(74) * 6);
      g.fillStyle = '#1e1e23'; g.beginPath(); g.roundRect(0, 0, 370, 190, 22); g.fill();
      g.fillStyle = TYPECOL.PDF; g.beginPath(); g.roundRect(22, 24, 76, 92, 10); g.fill(); T(g, 'PDF', 60, 80, { f: 'Inter', w: 800, sz: 22, c: '#fff', al: 'center' });
      T(g, 'launch-plan.pdf', 116, 62, { f: 'Inter', w: 700, sz: 26, c: COL.cream }); T(g, '184 KB · preserved v1', 116, 98, { f: 'JetBrains Mono', w: 500, sz: 18, c: COL.dim });
      T(g, 'from your 3rd most recent save', 22, 160, { f: 'Inter', w: 600, sz: 20, c: COL.y });
      g.restore();
    }
    return fx;
  }
  if (b < 80) { // metadata
    bg(g, TEX.concrete);
    ['TITLES.', 'TAGS.', 'CONTEXT.'].forEach((s, i) => { if (b >= 76 + i) slam(g, s, 110, 330 + i * 210, on(76 + i), { sz: 200, c: i === 1 ? COL.y : COL.cream }); });
    if (b >= 79) T(g, 'Drafted by your configured model. You approve.', 116, 930, { f: 'JetBrains Mono', w: 700, sz: 28, c: COL.cream });
    const fx0 = 980, fy0 = 220, fw = 820;
    g.fillStyle = '#0d0d10'; g.fillRect(fx0, fy0, fw, 640); g.strokeStyle = COL.cream; g.lineWidth = 3; g.strokeRect(fx0, fy0, fw, 640);
    T(g, 'ADD DELIVERY', fx0 + 34, fy0 + 66, { f: 'Anton', sz: 44, c: COL.cream, ls: 2 });
    const fields = [['TITLE', 'Northstar launch kit', 76.3], ['DESCRIPTION', 'Launch plan + cover art, kept together.', 77.1]];
    fields.forEach(([k, v, bb], i) => {
      const y = fy0 + 130 + i * 150; T(g, k, fx0 + 34, y, { f: 'JetBrains Mono', w: 800, sz: 20, c: COL.dim, ls: 3 });
      g.fillStyle = '#18181d'; g.fillRect(fx0 + 34, y + 16, fw - 68, 74); g.strokeStyle = 'rgba(236,228,212,.2)'; g.lineWidth = 2; g.strokeRect(fx0 + 34, y + 16, fw - 68, 74);
      T(g, typed(v, bt(bb), t, 34), fx0 + 56, y + 66, { f: 'Inter', w: 600, sz: 30, c: COL.cream, maxW: fw - 110 });
    });
    const ty = fy0 + 430; T(g, 'TAGS', fx0 + 34, ty, { f: 'JetBrains Mono', w: 800, sz: 20, c: COL.dim, ls: 3 });
    ['launch', 'northstar', 'q4'].forEach((s, i) => { if (b >= 77.6 + i * 0.35) { const x = fx0 + 34 + [0, 170, 380][i]; g.fillStyle = COL.y; g.beginPath(); g.roundRect(x, ty + 22, [150, 190, 90][i], 56, 28); g.fill(); T(g, s, x + [150, 190, 90][i] / 2, ty + 60, { f: 'Inter', w: 800, sz: 26, c: COL.blk, al: 'center' }); } });
    g.fillStyle = COL.blue; g.beginPath(); g.roundRect(fx0 + fw - 200, fy0 + 560, 166, 56, 10); g.fill(); T(g, 'Save', fx0 + fw - 117, fy0 + 598, { f: 'Inter', w: 800, sz: 26, c: '#fff', al: 'center' });
    g.strokeStyle = COL.cream; g.lineWidth = 2; g.beginPath(); g.roundRect(fx0 + fw - 400, fy0 + 560, 180, 56, 10); g.stroke(); T(g, 'Generate', fx0 + fw - 310, fy0 + 598, { f: 'Inter', w: 700, sz: 26, c: COL.cream, al: 'center' });
    return fx;
  }
  if (b < 88) { // privacy
    bg(g, TEX.concrete, 1, 0, 0, 1.03);
    fill(g, '#000', 0.25);
    const ws = ['NO AUTO-CAPTURE.', 'NO FOLDER SCAN.', 'NO ANALYTICS.', 'NO REMOTE INDEX.'];
    ws.forEach((s, i) => { const bb = 80 + i * 2; if (b >= bb) { const u = on(bb); g.fillStyle = i % 2 ? COL.y : COL.cream; g.save(); g.translate(100, 190 + i * 190); g.scale(slamS(u), slamS(u)); g.fillRect(0, 0, 18, 150); g.restore(); slam(g, s, 150, 330 + i * 190, u, { sz: 165, c: i % 2 ? COL.y : COL.cream, maxW: 1000 }); } });
    if (b >= 87) label(g, 1520, 560, 0.08, on(87), { title: 'LOCAL', rows: ['YOUR BACKEND PROFILE', 'NO PLUGIN ANALYTICS', 'NOTHING PHONES HOME'], badge: '✓', seed: 77, sc: 1.05 });
    return fx;
  }
  if (b < 92) { // your call
    fill(g, COL.y); g.fillStyle = TEX.dots; g.fillRect(0, 0, W, H);
    slam(g, 'NOTHING JOINS', 110, 330, on(88), { sz: 210, c: COL.blk });
    if (b >= 89) slam(g, 'THE SHELF', 110, 540, on(89), { sz: 210, c: COL.blk });
    if (b >= 90) { const u = on(90); spray(g, 'until you say so.', 140, 800, 150, eo(u / 0.6), { c: COL.blk, out: COL.y, rot: -0.04, seed: 31, dt: u, drips: 10 }); }
    if (b >= 91) T(g, 'THE FIRST SAVE IS YOUR CHOICE.', 1810, 950, { f: 'JetBrains Mono', w: 800, sz: 30, c: COL.blk, al: 'right', ls: 3 });
    fx.split = 1;
    return fx;
  }
  // riser b92–96
  const u = on(92), p = clamp(u / (bt(96) - bt(92)));
  fill(g, COL.blk);
  bg(g, TEX.heroDuo, 0.18 + p * 0.25, 0, 0, 1 + p * 0.3);
  for (let i = 0; i < 14; i++) { const y = ((i / 14 + t * 0.9 * (0.6 + p)) % 1) * H; g.fillStyle = `rgba(244,197,66,${0.05 + p * 0.12})`; g.fillRect(0, y, W, 4 + p * 10); }
  const nums = [[93, '3'], [94, '2'], [95, '1']];
  for (const [bb, s] of nums) if (b >= bb && b < bb + 1) T(g, s, W / 2, H / 2 + 330, { sz: 900, c: null, stroke: COL.y, lw: 6, al: 'center', sc: slamS(on(bb)), a: 0.55 });
  slam(g, 'SAVE IT.', W / 2, H / 2 + 120, u, { sz: 330, c: COL.cream, al: 'center', sc: 1 + ei(p) * 0.6 });
  fx.shake = 0.3 + p * 2.2; fx.split = 3 + p * 18; fx.glitch = p * p * 0.8; fx.zoom = 1 + p * 0.06;
  return fx;
}

// S6 DROP: b96 – b112
const DROPWORDS = ['KEEP', 'THE', 'WORK.', '*', 'SKIP', 'THE', 'HUNT.', '*'];
function s6(g, t) {
  const b = beatF(t), fx = { hud: 0.6, split: 4 + A('low') * 8, shake: 1.6 };
  if (b < 104) {
    const i = Math.floor(b - 96), u = t - bt(96 + i), wd = DROPWORDS[i];
    if (wd === '*') {
      bg(g, TEX.heroDuo, 1, 0, 0, 1.1 - u * 0.05);
      g.fillStyle = TEX.dots; g.fillRect(0, 0, W, H);
      g.save(); g.globalAlpha = 0.92; g.fillStyle = COL.blk; g.fillRect(0, H / 2 - 230, W, 460); g.restore();
      mark(g, W / 2, H / 2 + 20, 0.62 * slamS(u));
      fx.glitch = 0.5; fx.flash = { c: '#fff', a: Math.exp(-u * 10) * 0.6 };
    } else {
      const pal = [[COL.y, COL.blk], [COL.blk, COL.cream], [COL.blk, COL.y]];
      const [bgc, fc] = pal[i % 4 === 3 ? 0 : (i % 4)];
      fill(g, bgc); if (bgc === COL.y) { g.fillStyle = TEX.dots; g.fillRect(0, 0, W, H); } else bg(g, TEX.concrete, 0.6);
      hexStream(g, t, 40, 40, 40, 46, { c: bgc === COL.y ? 'rgba(0,0,0,0.08)' : 'rgba(244,197,66,0.06)', sz: 16, lh: 23, rate: 30 });
      slam(g, wd, W / 2, H / 2 + 250, u, { sz: 680, c: fc, al: 'center', maxW: 1750 });
      fx.flash = { c: '#fff', a: Math.exp(-u * 14) * 0.35 };
    }
    return fx;
  }
  // sticker bomb b104–112
  const u = t - bt(104);
  bg(g, TEX.heroHT, 1, 0, 0, 1.05 + u * 0.02);
  skyline(g, t, H - 460, 1, 1);
  const SK = [
    ['l', 'DELIVERY SHELF', 'v1'], ['s', 'KEEP THE WORK', COL.y], ['s', '/shelf add', COL.cream], ['l', 'PRESERVED COPY', 'v2'],
    ['s', 'SKIP THE HUNT', COL.y], ['s', 'TOGETHER', '#7aa6ff'], ['s', 'FOR HERMES AGENT', COL.cream], ['l', 'LAUNCH KIT', 'v3'],
    ['s', 'VERSIONS', COL.y], ['s', 'NO AUTO-CAPTURE', COL.cream], ['s', 'LIBRARY', '#7aa6ff'], ['l', 'YOUR SHELF', '✓'],
    ['s', 'GALLERY', COL.y], ['s', '/shelf r3', COL.cream],
  ];
  const r = rng(404);
  const pos = SK.map(() => [200 + r() * 1520, 170 + r() * 740, (r() - .5) * 0.5]);
  SK.forEach((s, i) => {
    const on = t - bt(104 + i * 0.5); if (on < 0) return;
    const [x, y, rot] = pos[i];
    if (s[0] === 'l') label(g, x, y, rot, on, { title: s[1], badge: s[2], seed: 50 + i, sc: 0.8 });
    else sticker(g, x, y, rot, on, s[1], { sz: 64, bg: s[2], f: s[1][0] === '/' ? 'JetBrains Mono' : 'Anton' });
  });
  if (b >= 108) tape(g, W / 2, H / 2 - 260, -0.12, 2600, 110, t * 900, 'DELIVERY SHELF', eo((t - bt(108)) / 0.3));
  if (b >= 109) tape(g, W / 2, H / 2 + 300, 0.1, 2600, 90, -t * 900, null, eo((t - bt(109)) / 0.3));
  if (b >= 110) {
    const q = t - bt(110);
    g.save(); g.translate(W / 2, H / 2); g.scale(slamS(q), slamS(q)); g.rotate(-0.03);
    g.fillStyle = 'rgba(0,0,0,.6)'; g.fillRect(-760, -170, 1540, 360); g.fillStyle = COL.blk; g.fillRect(-780, -190, 1540, 360);
    g.strokeStyle = COL.y; g.lineWidth = 8; g.strokeRect(-780, -190, 1540, 360);
    T(g, 'DELIVERY SHELF', -10, 120, { sz: 270, c: COL.y, al: 'center', maxW: 1440 });
    g.restore();
  }
  fx.flash = { c: '#fff', a: kick(t) * 0.12 };
  return fx;
}

// S7 install: b112 – b120
function s7(g, t) {
  const b = beatF(t), lt = t - bt(112);
  bg(g, TEX.concrete, 1, 0, 0, 1.02 + lt * 0.006);
  hexStream(g, t, 60, 110, 46, 42, { c: 'rgba(236,228,212,0.045)', sz: 16, lh: 23, rate: 8 });
  slam(g, 'INSTALL IN ONE LINE.', 140, 250, t - bt(112) - 0.1, { f: 'Saira Stencil One', sz: 130, c: COL.cream, maxW: 1640 });
  const lines = [
    { at: bt(112) + 0.45, pre: '$ ', s: 'hermes plugins install mechkw/hermes-delivery-shelf --enable', cps: 34, w: 700 },
    { at: bt(116), s: '✓ delivery-shelf installed', c: COL.y, w: 700 },
    { at: bt(116) + 0.35, s: '✓ agent + desktop halves enabled', c: COL.y, w: 700 },
    { at: bt(118), s: '→ open Saved → Deliverables', c: COL.cream, w: 700 },
  ];
  terminal(g, 140, 320, 1640, 340, 'HERMES // BACKEND', lines, t, { sz: 34 });
  if (b >= 117) T(g, 'DESKTOP:  CAPABILITIES → PLUGINS → INSTALL FROM GIT', 140, 780, { f: 'JetBrains Mono', w: 800, sz: 30, c: COL.cream, ls: 2, a: clamp((t - bt(117)) * 4) });
  rain(g, t, 120, 0.12);
  return { hud: 1, split: 1.2 };
}

// S8 finale: b120 – b128
function s8(g, t) {
  const b = beatF(t), u = t - bt(120);
  fill(g, COL.blk);
  g.save(); g.globalAlpha = 0.55; g.beginPath(); g.rect(W * 0.52, 0, W, H); g.clip(); bg(g, TEX.heroHT, 1, 220 - u * 18, 0, 1.12); g.restore();
  const gr = g.createLinearGradient(W * 0.48, 0, W * 0.72, 0); gr.addColorStop(0, COL.blk); gr.addColorStop(1, 'rgba(10,10,11,0)'); g.fillStyle = gr; g.fillRect(W * 0.48, 0, W * 0.3, H);
  skyline(g, t, H - 330, 1, 1);
  mark(g, 330, 420, 0.42 * slamS(u));
  slam(g, 'DELIVERY', 600, 380, u - 0.05, { sz: 130, c: COL.cream, ls: 8 });
  slam(g, 'SHELF', 590, 640, u - 0.1, { sz: 300, c: COL.y });
  if (b >= 122) T(g, typed('KEEP THE WORK. SKIP THE HUNT.', bt(122), t, 30), 606, 720, { f: 'JetBrains Mono', w: 800, sz: 40, c: COL.cream, ls: 2 });
  if (b >= 124) tape(g, W / 2, H - 120, -0.02, 2600, 100, t * 520, 'PLUGIN FOR HERMES AGENT', eo((t - bt(124)) / 0.3));
  return { hud: 0.8, split: 3 + A('low') * 6, shake: 0.9, flash: { c: COL.y, a: Math.exp(-u * 8) * 0.7 + (b >= 126 ? kick(t) * 0.15 : 0) } };
}

// S9 end card: b128 – end
function s9(g, t) {
  fill(g, COL.blk);
  if (t < 77.55) return { hud: 0 };
  const u = t - 77.55;
  bg(g, TEX.concrete, 0.7);
  mark(g, W / 2, 360, 0.36 * slamS(u));
  T(g, 'DELIVERY SHELF', W / 2, 640, { sz: 150, c: COL.y, al: 'center', ls: 4, sc: slamS(u - 0.04) });
  T(g, 'github.com/mechkw/hermes-delivery-shelf', W / 2, 740, { f: 'JetBrains Mono', w: 700, sz: 40, c: COL.cream, al: 'center', a: clamp((u - 0.2) * 4) });
  T(g, '/shelf add', W / 2, 830, { f: 'JetBrains Mono', w: 800, sz: 34, c: COL.y, al: 'center', a: clamp((u - 0.45) * 4) });
  hudCorners(g, 0.5);
  const fade = clamp((t - 78.9) / 1.0);
  return { hud: 0, split: 6 * Math.exp(-u * 6), flash: { c: '#fff', a: Math.exp(-u * 10) * 0.6 }, fade };
}

const SCENES = [[0, bt(6), s1], [bt(6), bt(24), s2], [bt(24), bt(48), s3], [bt(48), bt(60), s4], [bt(60), bt(96), s5], [bt(96), bt(112), s6], [bt(112), bt(120), s7], [bt(120), bt(128), s8], [bt(128), 999, s9]];
const STOPS = [[28.50, bt(48)], [47.98, bt(80)], [57.46, bt(96)], [bt(112) - 0.01, bt(112) + 0.22]];

// ---------- post ----------
function post(t, fx) {
  const S = TEX.S;
  ctx.save();
  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  // shake + zoom pump
  const sh = (fx.shake || 0) * (4 + A('low') * 10) * kick(t);
  const dx = (hash(FR, 1) - .5) * 2 * sh, dy = (hash(FR, 2) - .5) * 2 * sh;
  const z = (fx.zoom || 1) * (1 + (fx.shake ? 0.012 * kick(t) : 0));
  const split = fx.split || 0;
  let src = S;
  if (split > 0.6) {
    const ch = [[TEX.R, '#f00'], [TEX.G, '#0f0'], [TEX.B, '#00f']];
    for (const [c, col] of ch) { const g = c.getContext('2d'); g.globalCompositeOperation = 'copy'; g.drawImage(S, 0, 0); g.globalCompositeOperation = 'multiply'; g.fillStyle = col; g.fillRect(0, 0, W, H); g.globalCompositeOperation = 'source-over'; }
    const tg = TEX.tmp.getContext('2d'); tg.globalCompositeOperation = 'copy'; tg.fillStyle = '#000'; tg.fillRect(0, 0, W, H);
    tg.globalCompositeOperation = 'lighter'; tg.drawImage(TEX.R, split, 0); tg.drawImage(TEX.G, 0, 0); tg.drawImage(TEX.B, -split, split * 0.3); tg.globalCompositeOperation = 'source-over';
    src = TEX.tmp;
  }
  ctx.translate(W / 2 + dx, H / 2 + dy); ctx.scale(z, z); ctx.drawImage(src, -W / 2, -H / 2); ctx.setTransform(1, 0, 0, 1, 0, 0);
  // slice glitch
  const gl = fx.glitch || 0;
  if (gl > 0.02) {
    const n = Math.floor(gl * 14);
    for (let i = 0; i < n; i++) {
      const y = hash(FR, i * 3) * H, h = 6 + hash(FR, i * 3 + 1) * 90 * gl, off = (hash(FR, i * 3 + 2) - .5) * 260 * gl;
      ctx.drawImage(src === S ? S : TEX.tmp, 0, y, W, h, off, y, W, h);
      if (hash(i, FR) < 0.25 * gl) { ctx.fillStyle = hash(i, 9) < .5 ? 'rgba(244,197,66,.6)' : 'rgba(47,107,255,.5)'; ctx.fillRect(hash(i, FR + 3) * W, y, 40 + hash(i, 4) * 300, h * 0.4); }
    }
  }
  if (fx.hud) hud(ctx, t, fx.hud, fx.hudBottom !== false);
  // flash
  if (fx.flash && fx.flash.a > 0.01) { ctx.globalAlpha = clamp(fx.flash.a); ctx.fillStyle = fx.flash.c; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
  // texture: scanlines, grain, vignette
  ctx.globalAlpha = 0.18; ctx.fillStyle = TEX.scan; ctx.fillRect(0, 0, W, H);
  ctx.globalAlpha = 0.07; ctx.globalCompositeOperation = 'overlay';
  const gt = TEX.grain[FR % 3], ox = Math.floor(hash(FR, 7) * 256), oy = Math.floor(hash(FR, 8) * 256);
  const pat = ctx.createPattern(gt, 'repeat'); ctx.translate(-ox, -oy); ctx.fillStyle = pat; ctx.fillRect(0, 0, W + 256, H + 256); ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 0.85; ctx.drawImage(TEX.vig, 0, 0); ctx.globalAlpha = 1;
  // stops: CRT collapse
  for (const [a, b] of STOPS) {
    if (t >= a && t < b) {
      const u = t - a; const q = clamp(u / 0.09);
      const snap = mk1(); const sg = snap.getContext('2d'); sg.drawImage(C, 0, 0);
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
      if (q < 1) { const hh = Math.max(4, H * (1 - q)); ctx.drawImage(snap, 0, (H - hh) / 2, W, hh); }
      const lw = W * (1 - clamp((u - 0.09) / 0.12)); if (lw > 2) { ctx.fillStyle = '#fff'; ctx.fillRect((W - lw) / 2, H / 2 - 3, lw, 6); }
      if (b - a > 0.3) T(ctx, '■ HOLD', W - 80, H - 70, { f: 'JetBrains Mono', w: 800, sz: 20, c: COL.dim, al: 'right', a: clamp((u - 0.2) * 5) });
    }
  }
  if (fx.fade) { ctx.globalAlpha = clamp(fx.fade); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
  ctx.restore();
}
let _snap = null; function mk1() { return _snap || (_snap = mk(W, H)); }

// ---------- entry ----------
const IMG = {};
function loadImg(src) { return new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; }); }
window.renderFrame = function (i) {
  FR = i; const t = i / FPS;
  const g = TEX.S.getContext('2d');
  g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = 1; g.globalCompositeOperation = 'source-over'; g.shadowBlur = 0;
  let fx = {};
  for (const [a, b, fn] of SCENES) if (t >= a && t < b) { g.save(); fx = fn(g, t) || {}; g.restore(); break; }
  post(t, fx);
};
window.frameJPEG = function (i, q = 0.93) { window.renderFrame(i); return C.toDataURL('image/jpeg', q); };
(async () => {
  await Promise.all(['Anton', 'Permanent Marker', 'Saira Stencil One'].map(f => document.fonts.load(`40px "${f}"`)));
  await document.fonts.load('700 40px "JetBrains Mono"'); await document.fonts.load('800 40px "JetBrains Mono"'); await document.fonts.load('500 40px "JetBrains Mono"');
  await document.fonts.load('800 40px "Inter"'); await document.fonts.load('600 40px "Inter"'); await document.fonts.load('700 40px "Inter"');
  IMG.hero = await loadImg('assets/hero.png'); IMG.tog = await loadImg('assets/dark-together.png'); IMG.lib = await loadImg('assets/dark-library.png');
  AUD = window.AUDIO || null;
  buildTextures(IMG);
  window.READY = true;
})().catch(e => { window.ERR = String(e && e.stack || e); });
