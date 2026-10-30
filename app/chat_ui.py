"""Print247 chat UI — visual layer only.

The FastAPI routes, /chat payload and all JS contracts still live where
they were. This module owns only the page: tokens, layout, motion and
render helpers. Keep the IDs/functions documented in web.py intact.
"""

CHAT_HTML = r"""<!doctype html>
<html lang="en" data-theme="midnight">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">
<meta name="theme-color" content="#08090a" id="themeColor">
<title>Print247 — Packaging studio</title>
<script>
/* Set the saved theme before paint so the toggle never flashes. */
try {
  var savedTheme = localStorage.getItem('p247_theme');
  if (savedTheme === 'midnight' || savedTheme === 'kraft' || savedTheme === 'light') {
    document.documentElement.dataset.theme = savedTheme;
  }
} catch (e) {}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&amp;family=Instrument+Sans:wght@400;500;600&amp;display=swap" rel="stylesheet">
<style>
/* ============================================================
   1. TOKENS
   One place to re-theme. Every surface, text and border below
   reads from these variables.
   ============================================================ */
:root {
  --font-display: "Bricolage Grotesque", "Trebuchet MS", "Avenir Next", sans-serif;
  --font-body: "Instrument Sans", "Helvetica Neue", Arial, sans-serif;
  --font-mono: "SFMono-Regular", "Cascadia Code", "Roboto Mono", ui-monospace, monospace;

  --r-xl: 26px;
  --r-lg: 20px;
  --r-md: 14px;
  --r-sm: 10px;
}

/* Midnight Orange — default dark */
:root,
[data-theme="midnight"] {
  color-scheme: dark;
  --bg: #08090a;
  --bg-2: #0c0d0f;
  --shell-bg: linear-gradient(180deg, #111214 0%, #0b0c0e 100%);
  --shell-highlight: rgba(255, 255, 255, .06);
  --surface: #16171a;
  --surface-2: #1e1f23;
  --surface-3: #27282d;
  --header-bg: rgba(15, 16, 18, .74);
  --composer-bg: rgba(10, 11, 13, .82);
  --field-bg: #141518;
  --field-shadow: inset 0 1px 0 rgba(255, 255, 255, .03);
  --border: rgba(255, 255, 255, .08);
  --border-strong: rgba(255, 255, 255, .16);
  --text: #f3efe7;
  --text-2: #b8afa2;
  --text-3: #91887b;
  --accent: #ff6a2b;
  --accent-hover: #ff814c;
  --accent-deep: #dd5117;
  --accent-ink: #1c0d05;
  --accent-text: #ff9f73;
  --accent-soft: rgba(255, 106, 43, .10);
  --accent-soft-strong: rgba(255, 106, 43, .22);
  --accent-border: rgba(255, 106, 43, .30);
  --accent-ring: rgba(255, 106, 43, .18);
  --accent-glow: rgba(255, 106, 43, .30);
  --success: #78e3aa;
  --success-soft: rgba(120, 227, 170, .12);
  --success-border: rgba(120, 227, 170, .26);
  --success-ring: rgba(120, 227, 170, .40);
  --danger: #ff8080;
  --danger-soft: rgba(255, 128, 128, .10);
  --danger-border: rgba(255, 128, 128, .28);
  --kraft: #d8b58a;
  --kraft-deep: #b98e60;
  --bubble-1: #1b1c20;
  --bubble-2: #16171a;
  --bubble-border: rgba(255, 255, 255, .075);
  --bubble-link: #ffab82;
  --shadow-bubble: 0 14px 28px -24px rgba(0, 0, 0, .9);
  --user-1: #f0d9b8;
  --user-2: #d9b98d;
  --user-ink: #24160a;
  --user-border: rgba(255, 255, 255, .08);
  --user-fold: rgba(112, 74, 35, .35);
  --quote-bg: rgba(36, 20, 8, .09);
  --quote-line: rgba(36, 20, 8, .28);
  --quote-card-bg: rgba(255, 255, 255, .02);
  --code-bg: rgba(0, 0, 0, .28);
  --dot: rgba(255, 255, 255, .055);
  --dieline: rgba(255, 255, 255, .06);
  --glow-a: rgba(255, 106, 43, .10);
  --glow-b: rgba(216, 181, 138, .05);
  --grain-opacity: .05;
  --card: rgba(255, 255, 255, .024);
  --card-hover: rgba(255, 255, 255, .048);
  --chip-ico: rgba(255, 255, 255, .05);
  --tooltip-bg: #f3efe7;
  --tooltip-text: #16171a;
  --skeleton-base: #1c1d21;
  --skeleton-shine: #292a30;
  --toast-bg: #1e1f23;
  --toast-text: #f3efe7;
  --scroll-thumb: rgba(255, 255, 255, .16);
  --focus: #ffb48c;
}

/* Kraft Warm — warm paper light */
[data-theme="kraft"] {
  color-scheme: light;
  --bg: #e9ddca;
  --bg-2: #f2e8d8;
  --shell-bg: linear-gradient(180deg, #fcf7ee 0%, #f6eee1 100%);
  --shell-highlight: rgba(255, 255, 255, .70);
  --surface: #f4eadb;
  --surface-2: #fffaf2;
  --surface-3: #eee3d3;
  --header-bg: rgba(252, 247, 238, .80);
  --composer-bg: rgba(251, 244, 233, .86);
  --field-bg: #fffdf8;
  --field-shadow: inset 0 1px 0 rgba(255, 255, 255, .80);
  --border: rgba(52, 35, 17, .13);
  --border-strong: rgba(52, 35, 17, .22);
  --text: #221a12;
  --text-2: #5c5043;
  --text-3: #786a59;
  --accent: #b8430d;
  --accent-hover: #9e390a;
  --accent-deep: #873008;
  --accent-ink: #fff8ee;
  --accent-text: #a43c0b;
  --accent-soft: rgba(184, 67, 13, .08);
  --accent-soft-strong: rgba(184, 67, 13, .16);
  --accent-border: rgba(184, 67, 13, .28);
  --accent-ring: rgba(184, 67, 13, .14);
  --accent-glow: rgba(184, 67, 13, .18);
  --success: #147a48;
  --success-soft: rgba(20, 122, 72, .10);
  --success-border: rgba(20, 122, 72, .24);
  --success-ring: rgba(20, 122, 72, .28);
  --danger: #b3261e;
  --danger-soft: rgba(179, 38, 30, .08);
  --danger-border: rgba(179, 38, 30, .24);
  --kraft: #c9a374;
  --kraft-deep: #a77f4f;
  --bubble-1: #fffdf8;
  --bubble-2: #fbf6ed;
  --bubble-border: rgba(52, 35, 17, .10);
  --bubble-link: #9e390a;
  --shadow-bubble: 0 14px 26px -26px rgba(70, 45, 18, .35);
  --user-1: #2b2117;
  --user-2: #1b140d;
  --user-ink: #f8ecd9;
  --user-border: rgba(255, 255, 255, .06);
  --user-fold: rgba(255, 255, 255, .12);
  --quote-bg: rgba(255, 255, 255, .08);
  --quote-line: rgba(255, 255, 255, .22);
  --quote-card-bg: rgba(255, 255, 255, .55);
  --code-bg: rgba(52, 35, 17, .07);
  --dot: rgba(52, 35, 17, .09);
  --dieline: rgba(52, 35, 17, .09);
  --glow-a: rgba(184, 67, 13, .08);
  --glow-b: rgba(201, 163, 116, .30);
  --grain-opacity: .035;
  --card: rgba(255, 255, 255, .55);
  --card-hover: rgba(255, 255, 255, .90);
  --chip-ico: rgba(52, 35, 17, .05);
  --tooltip-bg: #241b12;
  --tooltip-text: #fff8ee;
  --skeleton-base: #efe5d6;
  --skeleton-shine: #faf3e8;
  --toast-bg: #241b12;
  --toast-text: #fbf6ed;
  --scroll-thumb: rgba(52, 35, 17, .20);
  --focus: #8a3408;
}

/* Clean Light — neutral studio light */
[data-theme="light"] {
  color-scheme: light;
  --bg: #eef0ed;
  --bg-2: #f6f7f5;
  --shell-bg: linear-gradient(180deg, #fefefd 0%, #f8faf7 100%);
  --shell-highlight: rgba(255, 255, 255, .80);
  --surface: #f3f5f1;
  --surface-2: #ffffff;
  --surface-3: #e9ece7;
  --header-bg: rgba(255, 255, 255, .82);
  --composer-bg: rgba(255, 255, 255, .86);
  --field-bg: #ffffff;
  --field-shadow: inset 0 1px 0 rgba(255, 255, 255, .90);
  --border: rgba(20, 30, 22, .10);
  --border-strong: rgba(20, 30, 22, .18);
  --text: #151a17;
  --text-2: #4f5a53;
  --text-3: #6b766e;
  --accent: #b8460a;
  --accent-hover: #9f3c07;
  --accent-deep: #853206;
  --accent-ink: #ffffff;
  --accent-text: #a44109;
  --accent-soft: rgba(184, 70, 10, .07);
  --accent-soft-strong: rgba(184, 70, 10, .14);
  --accent-border: rgba(184, 70, 10, .26);
  --accent-ring: rgba(184, 70, 10, .13);
  --accent-glow: rgba(184, 70, 10, .16);
  --success: #187a4e;
  --success-soft: rgba(24, 122, 78, .09);
  --success-border: rgba(24, 122, 78, .22);
  --success-ring: rgba(24, 122, 78, .26);
  --danger: #b3261e;
  --danger-soft: rgba(179, 38, 30, .07);
  --danger-border: rgba(179, 38, 30, .22);
  --kraft: #c9a374;
  --kraft-deep: #a77f4f;
  --bubble-1: #ffffff;
  --bubble-2: #fbfcfa;
  --bubble-border: rgba(20, 30, 22, .08);
  --bubble-link: #9f3c07;
  --shadow-bubble: 0 14px 26px -26px rgba(20, 40, 25, .25);
  --user-1: #23262a;
  --user-2: #15181b;
  --user-ink: #f7f4ec;
  --user-border: rgba(255, 255, 255, .05);
  --user-fold: rgba(255, 255, 255, .10);
  --quote-bg: rgba(255, 255, 255, .08);
  --quote-line: rgba(255, 255, 255, .22);
  --quote-card-bg: rgba(255, 255, 255, .70);
  --code-bg: rgba(20, 30, 22, .06);
  --dot: rgba(20, 30, 22, .07);
  --dieline: rgba(20, 30, 22, .07);
  --glow-a: rgba(184, 70, 10, .06);
  --glow-b: rgba(60, 110, 80, .05);
  --grain-opacity: .03;
  --card: rgba(255, 255, 255, .70);
  --card-hover: #ffffff;
  --chip-ico: rgba(20, 30, 22, .045);
  --tooltip-bg: #151a17;
  --tooltip-text: #ffffff;
  --skeleton-base: #e9ece8;
  --skeleton-shine: #f8faf7;
  --toast-bg: #151a17;
  --toast-text: #ffffff;
  --scroll-thumb: rgba(20, 30, 22, .18);
  --focus: #8a3408;
}

/* ============================================================
   2. BASE
   ============================================================ */
*, *::before, *::after { box-sizing: border-box; }
html { height: 100%; -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  overscroll-behavior: none;
}
button, textarea { font: inherit; color: inherit; }
button { cursor: pointer; }
button:disabled { cursor: not-allowed; }
a { color: var(--accent-text); }
::selection { background: var(--accent-soft-strong); color: var(--text); }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
[hidden] { display: none !important; }
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}
.svg-sprite { position: absolute; width: 0; height: 0; overflow: hidden; }
.icon, .mark-svg {
  width: 18px; height: 18px; flex: none; fill: none; stroke: currentColor;
  stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round;
}

/* ============================================================
   3. ATMOSPHERE — crop marks, dotted grid, box-fold lines, grain
   ============================================================ */
.ambient {
  position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none;
}
.orb { position: absolute; border-radius: 50%; }
.orb-a {
  width: 70vw; height: 52vw; left: -22vw; top: -24vw;
  background: radial-gradient(closest-side, var(--glow-a), transparent 72%);
}
.orb-b {
  width: 62vw; height: 52vw; right: -18vw; bottom: -24vw;
  background: radial-gradient(closest-side, var(--glow-b), transparent 72%);
}
.grid {
  position: absolute; inset: 0;
  background-image: radial-gradient(circle at 1px 1px, var(--dot) 1px, transparent 0);
  background-size: 24px 24px;
  -webkit-mask-image: radial-gradient(ellipse at 50% 42%, #000 0%, transparent 78%);
  mask-image: radial-gradient(ellipse at 50% 42%, #000 0%, transparent 78%);
}
.dieline {
  position: absolute; border: 1px dashed var(--dieline); border-radius: 10px;
}
.dieline::before {
  content: ""; position: absolute; inset: 18% 32%;
  border-left: 1px dashed var(--dieline); border-right: 1px dashed var(--dieline);
}
.dieline::after {
  content: ""; position: absolute; inset: 38% 10%;
  border-top: 1px dashed var(--dieline); border-bottom: 1px dashed var(--dieline);
}
.dieline.d1 { width: 620px; height: 440px; right: -140px; top: 8%; transform: rotate(-9deg); }
.dieline.d2 { width: 430px; height: 300px; right: 3%; top: 23%; transform: rotate(11deg); opacity: .6; }
.grain {
  position: absolute; inset: -50%;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.55'/%3E%3C/svg%3E");
  background-size: 180px 180px;
  opacity: var(--grain-opacity);
  mix-blend-mode: overlay;
}
.crop { position: absolute; width: 18px; height: 18px; opacity: .55; }
.crop::before, .crop::after { content: ""; position: absolute; background: var(--dieline); }
.crop::before { left: 0; right: 0; top: 50%; height: 1px; }
.crop::after { top: 0; bottom: 0; left: 50%; width: 1px; }
.crop.tl { top: 22px; left: 22px; }
.crop.tr { top: 22px; right: 22px; }
.crop.bl { bottom: 22px; left: 22px; }
.crop.br { bottom: 22px; right: 22px; }

/* ============================================================
   4. SHELL + HEADER
   ============================================================ */
.wrap {
  position: relative; z-index: 1;
  min-height: 100vh; min-height: 100dvh;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.chat-shell {
  position: relative; isolation: isolate;
  display: flex; flex-direction: column;
  width: min(760px, 100%);
  height: min(900px, calc(100dvh - 48px));
  border: 1px solid var(--border);
  border-radius: 28px;
  background: var(--shell-bg);
  box-shadow:
    0 50px 110px -60px rgba(0, 0, 0, .85),
    0 0 0 1px var(--border);
  overflow: hidden;
  transition: opacity .2s ease, transform .2s ease, visibility .2s;
}
.chat-shell::before {
  content: ""; position: absolute; inset: 0; z-index: 9;
  border-radius: inherit; pointer-events: none;
  box-shadow: inset 0 1px 0 var(--shell-highlight);
}
.app-header {
  position: relative; z-index: 4; flex: none;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 16px 20px;
  background: var(--header-bg);
  border-bottom: 1px solid var(--border);
  -webkit-backdrop-filter: blur(20px) saturate(1.25);
  backdrop-filter: blur(20px) saturate(1.25);
}
.app-header::after {
  content: ""; position: absolute; left: 20px; right: 20px; bottom: -1px; height: 1px;
  background: linear-gradient(90deg, transparent, var(--accent-border), transparent);
  opacity: .55;
}
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.brand-mark {
  position: relative; display: grid; place-items: center;
  width: 44px; height: 44px; flex: 0 0 44px;
  background: linear-gradient(145deg, var(--accent-hover), var(--accent) 55%, var(--accent-deep));
  color: var(--accent-ink);
  clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 0 100%);
  filter: drop-shadow(0 9px 16px var(--accent-glow));
}
.brand-mark::after {
  content: ""; position: absolute; top: 0; right: 0; width: 12px; height: 12px;
  background: linear-gradient(225deg, rgba(255, 255, 255, .45) 0 48%, transparent 50%);
}
.brand-mark .mark-svg { width: 23px; height: 23px; stroke-width: 1.55; }
.brand-copy { min-width: 0; }
.brand-line { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.brand-name {
  margin: 0; white-space: nowrap;
  font-family: var(--font-display); font-size: 22px; font-weight: 700;
  letter-spacing: -.035em; line-height: 1; color: var(--text);
}
.brand-name span { color: var(--accent); }
.brand-tag {
  padding-left: 10px; border-left: 1px solid var(--border);
  font-size: 8.5px; font-weight: 700; letter-spacing: .16em;
  text-transform: uppercase; color: var(--text-3); white-space: nowrap;
}
.brand-status {
  display: flex; align-items: center; gap: 8px; margin-top: 6px;
  font-size: 11.5px; color: var(--text-3); white-space: nowrap; overflow: hidden;
}
.status { display: inline-flex; align-items: center; gap: 6px; color: var(--text-2); font-weight: 500; }
.dot, .pulse {
  width: 7px; height: 7px; border-radius: 50%; background: var(--success);
  box-shadow: 0 0 0 0 var(--success-ring);
  animation: pulse 2.6s ease-out infinite;
}
.status-sep { width: 1px; height: 10px; background: var(--border-strong); flex: none; }
.response-hint { overflow: hidden; text-overflow: ellipsis; }
.header-actions { display: flex; align-items: center; gap: 6px; flex: none; }
.icon-btn {
  position: relative; display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  height: 38px; min-width: 38px; padding: 0 10px;
  border: 1px solid transparent; border-radius: 11px;
  background: transparent; color: var(--text-2);
  transition: background-color .18s ease, border-color .18s ease, color .18s ease, transform .18s ease;
}
.icon-btn:hover { background: var(--surface-2); border-color: var(--border); color: var(--text); transform: translateY(-1px); }
.icon-btn:active { transform: scale(.95); }
.icon-btn .icon { width: 17px; height: 17px; }
.new-chat {
  background: var(--surface-2); border-color: var(--border); color: var(--text);
}
.new-chat-label { font-size: 12px; font-weight: 600; letter-spacing: .01em; white-space: nowrap; }
#themeToggle .icon-moon { display: none; }
[data-theme="kraft"] #themeToggle .icon-sun,
[data-theme="light"] #themeToggle .icon-sun { display: none; }
[data-theme="kraft"] #themeToggle .icon-moon,
[data-theme="light"] #themeToggle .icon-moon { display: block; }
.widget-only { display: none; }
body.widget-mode .widget-only { display: inline-flex; }
@media (hover: hover) {
  .icon-btn[data-tip]::after {
    content: attr(data-tip); position: absolute; top: calc(100% + 8px); right: 0;
    padding: 5px 8px; border-radius: 6px;
    background: var(--tooltip-bg); color: var(--tooltip-text);
    font-size: 10.5px; font-weight: 600; letter-spacing: .02em; white-space: nowrap;
    opacity: 0; transform: translateY(-3px); pointer-events: none;
    transition: opacity .16s ease, transform .16s ease; z-index: 30;
  }
  .icon-btn[data-tip]:hover::after,
  .icon-btn[data-tip]:focus-visible::after { opacity: 1; transform: none; }
}

/* ============================================================
   5. CHAT BODY + LOG
   ============================================================ */
.chat-body { position: relative; display: flex; flex-direction: column; flex: 1; min-height: 0; }
.log-wrap { position: relative; display: flex; flex: 1; min-height: 0; }
.log {
  position: relative; flex: 1; min-width: 0;
  overflow-y: auto; overflow-x: hidden;
  padding: 28px 26px 10px;
  background-image: radial-gradient(circle at 1px 1px, var(--dot) 1px, transparent 0);
  background-size: 24px 24px;
  scrollbar-width: thin;
  scrollbar-color: var(--scroll-thumb) transparent;
  scroll-behavior: smooth;
  overscroll-behavior: contain;
  outline: none;
}
.log::-webkit-scrollbar { width: 8px; }
.log::-webkit-scrollbar-thumb {
  background: var(--scroll-thumb); border-radius: 99px;
  border: 2px solid transparent; background-clip: padding-box;
}
.log:focus-visible { box-shadow: inset 0 0 0 2px var(--accent-border); }

/* ============================================================
   6. WELCOME HERO
   ============================================================ */
.welcome {
  max-width: 600px; margin: max(2vh, 10px) auto 24px; padding: 6px 2px;
  animation: rise .24s ease-out both;
}
.welcome-kicker {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 10px; border: 1px solid var(--accent-border); border-radius: 999px;
  background: var(--accent-soft); color: var(--accent-text);
  font-size: 9px; font-weight: 700; letter-spacing: .18em; text-transform: uppercase;
}
.welcome-kicker .icon { width: 13px; height: 13px; }
.welcome h2 {
  margin: 20px 0 14px; text-wrap: balance;
  font-family: var(--font-display); font-size: clamp(32px, 4.6vw, 46px);
  font-weight: 650; line-height: 1.02; letter-spacing: -.035em; color: var(--text);
}
.welcome h2 em {
  position: relative; font-style: normal; color: var(--accent); white-space: nowrap;
  padding-bottom: 5px;
  background-image: linear-gradient(90deg, var(--accent-border) 45%, transparent 45%);
  background-repeat: repeat-x; background-size: 6px 2px; background-position: 0 100%;
}
.welcome p { max-width: 47ch; margin: 0; color: var(--text-2); font-size: 14.5px; line-height: 1.65; }
.welcome-rule {
  display: flex; align-items: center; gap: 12px; margin: 26px 0 12px;
  font-size: 9px; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; color: var(--text-3);
}
.welcome-rule::after {
  content: ""; flex: 1; height: 1px;
  background: repeating-linear-gradient(90deg, var(--border-strong) 0 4px, transparent 4px 8px);
}
.starters { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
.starter {
  position: relative; display: flex; align-items: center; gap: 11px;
  min-height: 64px; padding: 11px 12px;
  border: 1px solid var(--border); border-radius: 14px;
  background: var(--card); color: var(--text); text-align: left;
  transition: transform .18s ease, border-color .18s ease, background-color .18s ease, box-shadow .18s ease;
  animation: rise .24s cubic-bezier(.2, .8, .2, 1) both;
  animation-delay: calc(var(--i, 0) * 45ms + 60ms);
}
.starter:hover {
  transform: translateY(-2px); border-color: var(--accent-border); background: var(--card-hover);
  box-shadow: 0 16px 30px -24px var(--accent-glow);
}
.starter:active { transform: scale(.985); }
.starter-ico {
  display: grid; place-items: center; width: 38px; height: 38px; flex: 0 0 38px;
  border: 1px solid var(--border); border-radius: 11px;
  background: var(--surface-2); color: var(--accent);
  transition: background-color .18s ease, color .18s ease;
}
.starter:hover .starter-ico { background: var(--accent-soft); color: var(--accent-text); }
.starter-ico .icon { width: 19px; height: 19px; }
.starter-copy { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.starter-copy strong { font-size: 13px; font-weight: 600; line-height: 1.2; letter-spacing: -.01em; }
.starter-copy small { color: var(--text-3); font-size: 11px; line-height: 1.3; }
.starter-arrow { width: 13px; height: 13px; margin-left: auto; color: var(--text-3); transition: color .18s ease, transform .18s ease; }
.starter:hover .starter-arrow { color: var(--accent-text); transform: translateX(2px); }
.welcome-meta {
  display: flex; align-items: center; gap: 8px; margin-top: 20px;
  color: var(--text-3); font-size: 10.5px; letter-spacing: .02em;
}
.welcome-meta .status { font-size: 10.5px; }

/* ============================================================
   7. MESSAGE ROWS + BUBBLES
   ============================================================ */
.row {
  display: flex; align-items: flex-start; gap: 10px; margin: 0 0 16px;
  animation: msgIn .24s cubic-bezier(.2, .8, .2, 1) both;
}
.row.me { justify-content: flex-end; }
.row.grouped { margin-top: -8px; }
.row.grouped .avatar { visibility: hidden; }
.avatar {
  display: grid; place-items: center; width: 30px; height: 30px; flex: 0 0 30px;
  margin-top: 2px;
  background: linear-gradient(145deg, var(--accent-hover), var(--accent));
  color: var(--accent-ink);
  clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 0 100%);
  filter: drop-shadow(0 6px 10px var(--accent-glow));
}
.avatar .mark-svg { width: 16px; height: 16px; stroke-width: 1.8; }
.msg-stack {
  display: flex; flex-direction: column; align-items: flex-start; gap: 5px;
  max-width: min(84%, 560px); min-width: 0;
}
.row.me .msg-stack { align-items: flex-end; max-width: min(78%, 520px); }
.bubble {
  position: relative; max-width: 100%;
  padding: 12px 15px; border-radius: 18px;
  font-size: 14.5px; line-height: 1.62; letter-spacing: -.004em;
  overflow-wrap: anywhere;
}
.row.bot .bubble {
  background: linear-gradient(180deg, var(--bubble-1), var(--bubble-2));
  border: 1px solid var(--bubble-border);
  border-radius: 18px 18px 18px 5px;
  color: var(--text); white-space: normal;
  box-shadow: var(--shadow-bubble);
}
.row.bot .bubble::before {
  content: ""; position: absolute; left: -1px; top: 14px; bottom: 14px; width: 2px;
  border-radius: 3px;
  background: linear-gradient(180deg, var(--accent), var(--accent-border));
  opacity: .9;
}
.row.me .bubble {
  background: linear-gradient(135deg, var(--user-1), var(--user-2));
  border: 1px solid var(--user-border);
  border-radius: 18px 18px 5px 18px;
  color: var(--user-ink); white-space: pre-wrap;
  box-shadow: 0 14px 26px -24px rgba(0, 0, 0, .75);
}
.row.me .bubble::after {
  content: ""; position: absolute; right: 0; bottom: 0; width: 14px; height: 14px;
  background: var(--user-fold);
  clip-path: polygon(100% 0, 100% 100%, 0 100%);
  border-bottom-right-radius: 5px; opacity: .55;
}
.bubble p { margin: 0 0 .65em; }
.bubble p:last-child { margin-bottom: 0; }
.bubble strong { font-weight: 600; color: inherit; }
.bubble a { color: var(--bubble-link); text-decoration: underline; text-underline-offset: 2px; }
.bubble a:hover { color: var(--accent-hover); }
.row.me .bubble a { color: inherit; text-decoration-color: var(--user-fold); }
.bubble ul, .bubble ol { margin: .3em 0 .65em; padding-left: 1.15em; }
.bubble li { margin: .18em 0; padding-left: .15em; }
.bubble li::marker { color: var(--accent); }
.bubble h4 { margin: .25em 0 .4em; font-family: var(--font-display); font-size: 1.02em; letter-spacing: -.01em; }
.bubble code {
  padding: .08em .32em; border: 1px solid var(--border); border-radius: 5px;
  background: var(--code-bg); font-family: var(--font-mono); font-size: .86em;
}
.bubble pre.code-block {
  margin: .55em 0 .7em; padding: 10px 12px; overflow-x: auto;
  border: 1px solid var(--border); border-radius: 9px;
  background: var(--code-bg); font-size: 12px; line-height: 1.5;
}
.bubble pre.code-block code { padding: 0; border: 0; background: none; font-size: inherit; }
.quote {
  margin: 0 0 8px; padding: 7px 9px 7px 10px;
  border-left: 2px solid var(--quote-line); border-radius: 8px;
  background: var(--quote-bg); font-size: 11.5px; line-height: 1.45;
  font-weight: 400; opacity: .9; white-space: pre-wrap;
}
.quote-label {
  display: block; margin-bottom: 2px;
  font-size: 8px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase;
  opacity: .6;
}
.src {
  display: flex; flex-wrap: wrap; align-items: center; gap: 5px;
  padding: 0 4px; margin-top: 1px; color: var(--text-3); font-size: 10px;
}
.src-label {
  margin-right: 2px; font-size: 8.5px; font-weight: 700;
  letter-spacing: .14em; text-transform: uppercase; color: var(--text-3);
}
.src-item {
  display: inline-flex; align-items: center; gap: 4px; max-width: 240px;
  padding: 3px 7px; border: 1px solid var(--border); border-radius: 999px;
  background: var(--card); color: var(--text-2);
  font-family: var(--font-mono); font-size: 9.5px; text-decoration: none;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.src-item .icon { width: 10px; height: 10px; }
a.src-item:hover { border-color: var(--accent-border); color: var(--accent-text); }
.msg-meta {
  display: flex; align-items: center; gap: 8px; min-height: 20px; padding: 0 3px;
  opacity: 0; transform: translateY(-2px);
  transition: opacity .18s ease, transform .18s ease;
}
.row:hover .msg-meta, .row:focus-within .msg-meta { opacity: 1; transform: none; }
.row.me .msg-meta { justify-content: flex-end; }
.stamp { font-family: var(--font-mono); font-size: 9.5px; color: var(--text-3); letter-spacing: .02em; }
.replybtn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 5px; border: 0; border-radius: 6px;
  background: none; color: var(--text-3); font-size: 10.5px; font-weight: 500;
  transition: background-color .16s ease, color .16s ease;
}
.replybtn .icon { width: 11px; height: 11px; }
.replybtn:hover { background: var(--accent-soft); color: var(--accent-text); }
@media (hover: none) {
  .msg-meta { opacity: .72; transform: none; }
}

/* ============================================================
   8. TYPING, ERROR, CHIPS, QUOTE BRIEF, SKELETON
   ============================================================ */
.typing { display: flex; align-items: center; gap: 10px; min-height: 46px; padding: 10px 13px; }
.typing-boxes { display: flex; align-items: flex-end; gap: 3px; width: 29px; height: 20px; }
.typing-boxes i {
  display: block; width: 7px; height: 7px; border-radius: 2px;
  background: linear-gradient(180deg, var(--accent-hover), var(--accent));
  transform-origin: bottom center;
  animation: pack 1.2s cubic-bezier(.4, 0, .2, 1) infinite;
}
.typing-boxes i:nth-child(2) {
  animation-delay: .12s;
  background: linear-gradient(180deg, var(--kraft), var(--kraft-deep));
}
.typing-boxes i:nth-child(3) { animation-delay: .24s; }
.typing-copy { display: flex; flex-direction: column; gap: 1px; }
.typing-label { color: var(--text-2); font-size: 11.5px; font-weight: 600; letter-spacing: .01em; }
.typing-label::after { content: "…"; animation: blink 1.4s ease-in-out infinite; }
.typing-sub {
  color: var(--text-3); font-family: var(--font-mono); font-size: 8.5px;
  letter-spacing: .08em; text-transform: uppercase;
}
.row.error-row .bubble.error-bubble {
  display: flex; align-items: flex-start; gap: 10px; padding: 12px 13px;
  background: var(--danger-soft); border-color: var(--danger-border);
}
.error-icon { width: 16px; height: 16px; margin-top: 1px; color: var(--danger); }
.error-copy { display: flex; flex-direction: column; gap: 2px; font-size: 12.5px; line-height: 1.45; }
.error-copy strong { font-weight: 600; }
.error-copy span { color: var(--text-2); font-size: 11.5px; }
.retry-btn {
  display: inline-flex; align-items: center; gap: 5px; flex: none;
  margin-left: auto; padding: 6px 9px;
  border: 1px solid var(--danger-border); border-radius: 8px;
  background: var(--card); color: var(--text); font-size: 11px; font-weight: 600;
  transition: border-color .16s ease, color .16s ease;
}
.retry-btn:hover { border-color: var(--danger); color: var(--danger); }
.retry-btn .icon { width: 11px; height: 11px; }
.chips {
  display: flex; flex-wrap: wrap; gap: 6px; max-width: 100%; margin: 2px 0 0;
  transition: height .2s ease, opacity .18s ease, transform .18s ease;
}
.chips.is-used { opacity: 0; transform: translateY(4px); pointer-events: none; }
.chip {
  display: inline-flex; align-items: center; gap: 7px;
  min-height: 34px; padding: 5px 9px 5px 5px;
  border: 1px solid var(--border); border-radius: 10px;
  background: var(--card); color: var(--text-2);
  font-size: 12px; font-weight: 500; line-height: 1.2; text-align: left;
  transition: transform .18s ease, border-color .18s ease, background-color .18s ease, box-shadow .18s ease, color .18s ease;
  animation: chipIn .24s cubic-bezier(.2, .8, .2, 1) both;
  animation-delay: calc(var(--i, 0) * 35ms + 40ms);
}
.chip-ico {
  display: grid; place-items: center; width: 24px; height: 24px; flex: 0 0 24px;
  border-radius: 7px; background: var(--chip-ico); color: var(--accent);
  transition: background-color .18s ease, color .18s ease;
}
.chip-ico .icon { width: 14px; height: 14px; }
.chip-label { max-width: 210px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip-arrow { width: 12px; height: 12px; color: var(--text-3); opacity: 0; transform: translateX(-3px); transition: opacity .18s ease, transform .18s ease, color .18s ease; }
.chip:hover {
  transform: translateY(-2px); border-color: var(--accent-border);
  background: var(--card-hover); color: var(--text);
  box-shadow: 0 12px 20px -18px var(--accent-glow);
}
.chip:hover .chip-ico { background: var(--accent-soft); color: var(--accent-text); }
.chip:hover .chip-arrow { opacity: 1; transform: none; color: var(--accent-text); }
.chip:active { transform: scale(.97); box-shadow: none; }
.quote-card {
  position: relative; width: 100%; max-width: 100%; margin-top: 1px; overflow: hidden;
  padding: 12px 13px 10px;
  border: 1px dashed var(--border-strong); border-radius: 14px;
  background: var(--quote-card-bg);
  box-shadow: var(--shadow-bubble);
}
.quote-card::after {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: linear-gradient(180deg, var(--accent), var(--kraft)); opacity: .9;
}
.quote-head {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  margin-bottom: 9px; padding-left: 4px;
}
.quote-kicker {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 8.5px; font-weight: 700; letter-spacing: .15em;
  text-transform: uppercase; color: var(--text-3);
}
.quote-kicker .icon { width: 11px; height: 11px; color: var(--success); }
.quote-status {
  padding: 3px 7px; border: 1px solid var(--success-border); border-radius: 999px;
  background: var(--success-soft); color: var(--success);
  font-size: 9px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
}
.quote-rows { display: grid; gap: 0; padding-left: 4px; }
.quote-row {
  display: grid; grid-template-columns: 92px 1fr; gap: 10px;
  padding: 6px 0; border-bottom: 1px dotted var(--border-strong); font-size: 12px;
}
.quote-row:last-child { border-bottom: 0; }
.q-label {
  padding-top: 2px; color: var(--text-3);
  font-family: var(--font-mono); font-size: 9px; letter-spacing: .04em; text-transform: uppercase;
}
.q-value { color: var(--text); font-weight: 600; text-transform: capitalize; }
.quote-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  margin-top: 8px; padding: 8px 4px 0; border-top: 1px dashed var(--border);
}
.quote-note { max-width: 34ch; color: var(--text-3); font-size: 9.5px; line-height: 1.4; }
.quote-copy {
  display: inline-flex; align-items: center; gap: 5px; flex: none;
  padding: 5px 8px; border: 1px solid var(--border); border-radius: 7px;
  background: var(--card); color: var(--text-2); font-size: 10px; font-weight: 600; white-space: nowrap;
  transition: border-color .16s ease, color .16s ease;
}
.quote-copy:hover { border-color: var(--accent-border); color: var(--accent-text); }
.quote-copy .icon { width: 11px; height: 11px; }
.skeleton { display: flex; flex-direction: column; gap: 18px; padding: 6px 0; }
.sk-row { display: flex; align-items: flex-start; gap: 10px; }
.sk-row.me { justify-content: flex-end; }
.sk-avatar {
  width: 30px; height: 30px; flex: 0 0 30px; border-radius: 9px;
  background: var(--skeleton-base); animation: shimmer 1.4s linear infinite;
}
.sk-lines { display: flex; flex-direction: column; gap: 7px; width: min(62%, 420px); }
.sk-row.me .sk-lines { width: min(45%, 300px); }
.sk-line {
  height: 10px; border-radius: 99px;
  background: linear-gradient(90deg, var(--skeleton-base) 0%, var(--skeleton-shine) 50%, var(--skeleton-base) 100%);
  background-size: 200% 100%;
  animation: shimmer 1.4s linear infinite;
}
.sk-line:nth-child(2) { width: 78%; }
.sk-line:nth-child(3) { width: 52%; }

/* ============================================================
   9. SCROLL-TO-LATEST
   ============================================================ */
.scroll-btn {
  position: absolute; left: 50%; bottom: 10px; z-index: 5;
  display: inline-flex; align-items: center; justify-content: center;
  width: 36px; height: 36px;
  border: 1px solid var(--border-strong); border-radius: 50%;
  background: var(--surface-2); color: var(--text-2);
  box-shadow: 0 10px 24px -12px rgba(0, 0, 0, .65);
  opacity: 0; visibility: hidden; pointer-events: none;
  transform: translate(-50%, 8px);
  transition: opacity .2s ease, transform .2s ease, visibility .2s, color .16s, border-color .16s;
}
.scroll-btn.show { opacity: 1; visibility: visible; pointer-events: auto; transform: translate(-50%, 0); }
.scroll-btn:hover { border-color: var(--accent-border); color: var(--accent-text); }
.scroll-btn .icon { width: 15px; height: 15px; }
.scroll-badge {
  position: absolute; top: -5px; right: -6px;
  min-width: 16px; height: 16px; padding: 0 4px;
  border-radius: 99px; background: var(--accent); color: var(--accent-ink);
  font-family: var(--font-mono); font-size: 8.5px; font-weight: 700;
  display: grid; place-items: center;
}

/* ============================================================
   10. COMPOSER
   ============================================================ */
.composer {
  position: relative; z-index: 4; flex: none;
  padding: 10px 16px calc(10px + env(safe-area-inset-bottom));
  background: var(--composer-bg);
  border-top: 1px solid var(--border);
  -webkit-backdrop-filter: blur(20px) saturate(1.2);
  backdrop-filter: blur(20px) saturate(1.2);
}
.composer::before {
  content: ""; position: absolute; left: 16px; right: 16px; top: -1px; height: 1px;
  background: linear-gradient(90deg, transparent, var(--border-strong), transparent);
}
#replybar {
  display: none; align-items: center; gap: 8px;
  margin: 0 0 8px; padding: 8px 10px;
  border: 1px solid var(--border); border-left: 2px solid var(--accent);
  border-radius: 10px; background: var(--surface-2);
  animation: replyIn .18s ease-out;
}
.replybar-ico { display: grid; place-items: center; flex: none; color: var(--accent-text); }
.replybar-ico .icon { width: 13px; height: 13px; }
.replybar-copy { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.replybar-label { color: var(--text-3); font-size: 8px; font-weight: 700; letter-spacing: .13em; text-transform: uppercase; }
#replytext { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-2); font-size: 11.5px; }
.replybar-close {
  display: grid; place-items: center; width: 24px; height: 24px; flex: none;
  margin-left: auto; border: 0; border-radius: 6px; background: none; color: var(--text-3);
}
.replybar-close:hover { background: var(--surface-3); color: var(--text); }
.replybar-close .icon { width: 12px; height: 12px; }
.composer-form {
  display: flex; align-items: flex-end; gap: 6px; padding: 6px;
  border: 1px solid var(--border-strong); border-radius: 18px;
  background: var(--field-bg);
  box-shadow: var(--field-shadow);
  transition: border-color .18s ease, box-shadow .18s ease;
}
.composer-form:focus-within {
  border-color: var(--accent-border);
  box-shadow: 0 0 0 3px var(--accent-ring), 0 14px 30px -26px var(--accent-glow);
}
.composer-btn {
  display: grid; place-items: center; width: 34px; height: 34px; flex: 0 0 34px;
  border: 0; border-radius: 10px; background: none; color: var(--text-3);
  transition: background-color .16s ease, color .16s ease, transform .16s ease;
}
.composer-btn:hover { background: var(--surface-2); color: var(--accent-text); }
.composer-btn:active { transform: scale(.94); }
.composer-btn .icon { width: 16px; height: 16px; }
#q {
  flex: 1; min-width: 0; height: 36px; max-height: 132px;
  padding: 8px 2px 7px; border: 0; outline: 0; resize: none;
  background: transparent; color: var(--text);
  font-size: 14.5px; line-height: 1.5;
  scrollbar-width: none; overflow-y: auto;
}
#q::placeholder { color: var(--text-3); }
#q::-webkit-scrollbar { display: none; }
.send {
  position: relative; display: grid; place-items: center;
  width: 36px; height: 36px; flex: 0 0 36px;
  border: 0; border-radius: 11px;
  background: linear-gradient(145deg, var(--accent-hover), var(--accent));
  color: var(--accent-ink);
  box-shadow: 0 8px 18px -10px var(--accent-glow), inset 0 1px 0 rgba(255, 255, 255, .25);
  transition: transform .18s ease, box-shadow .18s ease, background-color .18s ease, opacity .18s ease;
}
.send:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 12px 24px -10px var(--accent-glow), inset 0 1px 0 rgba(255, 255, 255, .3);
}
.send:active:not(:disabled) { transform: scale(.94); }
.send:disabled { background: var(--surface-2); color: var(--text-3); box-shadow: none; opacity: .55; }
.send:focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }
.send-icon { width: 16px; height: 16px; stroke-width: 2; }
.send-spinner {
  display: none; width: 15px; height: 15px;
  border: 2px solid var(--text-3); border-top-color: transparent; border-radius: 50%;
  animation: spin .7s linear infinite;
}
.send[aria-busy="true"] .send-icon { display: none; }
.send[aria-busy="true"] .send-spinner { display: block; }
.note {
  display: flex; align-items: center; gap: 5px;
  margin: 8px 2px 0; color: var(--text-3); font-size: 10.5px; line-height: 1.4;
}
.note-icon { width: 11px; height: 11px; opacity: .8; }
.key-hint {
  display: inline-flex; align-items: center; gap: 3px; margin-left: auto;
  color: var(--text-3); font-size: 9.5px; white-space: nowrap;
}
kbd {
  padding: 1px 4px; border: 1px solid var(--border); border-bottom-color: var(--border-strong);
  border-radius: 4px; background: var(--surface-2);
  color: var(--text-2); font-family: var(--font-mono); font-size: 9px;
}
.toast {
  position: absolute; left: 50%; bottom: 104px; z-index: 20;
  max-width: min(90%, 420px); padding: 9px 12px;
  border: 1px solid var(--border-strong); border-radius: 10px;
  background: var(--toast-bg); color: var(--toast-text);
  font-size: 11.5px; line-height: 1.45;
  box-shadow: 0 18px 40px -20px rgba(0, 0, 0, .7);
  opacity: 0; pointer-events: none;
  transform: translate(-50%, 8px);
  transition: opacity .2s ease, transform .2s ease;
}
.toast.show { opacity: 1; transform: translate(-50%, 0); }

/* ============================================================
   11. REUSABLE RICH MESSAGE COMPONENTS
   Styled for structured payloads. The current API sends text +
   slots only, so the live thread uses the quote-card above.
   ============================================================ */
.product-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 8px; width: 100%; }
.product-card {
  display: flex; flex-direction: column; min-width: 0; overflow: hidden;
  border: 1px solid var(--border); border-radius: 14px; background: var(--card);
}
.product-media {
  display: grid; place-items: center; aspect-ratio: 16 / 9;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(135deg, var(--surface-2), var(--surface-3));
  color: var(--accent);
}
.product-media img { width: 100%; height: 100%; object-fit: cover; }
.product-media .icon { width: 28px; height: 28px; }
.product-body { display: flex; flex-direction: column; gap: 4px; padding: 10px 11px; }
.product-title { color: var(--text); font-size: 12.5px; font-weight: 600; }
.product-meta {
  color: var(--text-3); font-family: var(--font-mono); font-size: 9px;
  letter-spacing: .06em; text-transform: uppercase;
}
.product-cta {
  display: inline-flex; align-items: center; justify-content: center; gap: 5px;
  min-height: 28px; margin-top: 6px; padding: 5px 9px;
  border: 1px solid var(--accent-border); border-radius: 7px;
  background: var(--accent-soft); color: var(--accent-text);
  font-size: 10.5px; font-weight: 600; text-decoration: none;
}
.product-cta:hover { background: var(--accent); color: var(--accent-ink); }
.product-cta:disabled { opacity: .58; cursor: not-allowed; }
.option-group {
  display: flex; flex-direction: column; gap: 7px; width: 100%; padding: 10px 11px;
  border: 1px solid var(--border); border-radius: 12px; background: var(--card);
}
.option-group legend { padding: 0; }
.option-label { color: var(--text-3); font-size: 8.5px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
.option-list { display: flex; flex-wrap: wrap; gap: 6px; }
.option {
  display: inline-flex; align-items: center; gap: 6px;
  min-height: 30px; padding: 5px 9px;
  border: 1px solid var(--border); border-radius: 8px;
  background: var(--surface-2); color: var(--text-2);
  font-size: 11.5px; font-weight: 500;
  cursor: pointer;
}
.option-input {
  position: absolute; width: 1px; height: 1px; margin: 0;
  opacity: 0; overflow: hidden; clip-path: inset(50%);
}
.option:has(.option-input:checked) { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
.option:has(.option-input:checked) .option-dot { border-color: var(--accent); background: var(--accent); box-shadow: inset 0 0 0 2px var(--surface-2); }
.option-input:focus-visible + .option-dot { outline: 2px solid var(--focus); outline-offset: 3px; }
.option-dot {
  width: 9px; height: 9px; border: 1px solid var(--border-strong); border-radius: 50%;
  background: transparent;
}
.option[aria-pressed="true"] { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
.option[aria-pressed="true"] .option-dot { border-color: var(--accent); background: var(--accent); box-shadow: inset 0 0 0 2px var(--surface-2); }
.dropzone {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px;
  width: 100%; padding: 18px; text-align: center;
  border: 1px dashed var(--border-strong); border-radius: 14px;
  background: var(--card); color: var(--text-2);
  transition: border-color .18s ease, background-color .18s ease;
}
.dropzone[aria-disabled="true"] { cursor: not-allowed; }
.dropzone:hover, .dropzone.is-over { border-color: var(--accent); background: var(--accent-soft); }
.dropzone[aria-disabled="true"]:hover { border-color: var(--border-strong); background: var(--card); }
.dropzone .icon { width: 22px; height: 22px; color: var(--accent); }
.dropzone strong { color: var(--text); font-size: 12px; font-weight: 600; }
.dropzone small { color: var(--text-3); font-size: 10px; }
.file-chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 5px 8px;
  border: 1px solid var(--border); border-radius: 8px;
  background: var(--card); color: var(--text-2); font-size: 10.5px;
}
.file-chip .icon { width: 12px; height: 12px; color: var(--accent); }

/* ============================================================
   12. WIDGET MODE + LAUNCHER
   Add .widget-mode to <body>, or open the page with ?widget=1.
   ============================================================ */
body.widget-mode .wrap { align-items: flex-end; justify-content: flex-end; padding: 24px; }
body.widget-mode .chat-shell {
  width: min(420px, calc(100vw - 40px));
  height: min(720px, calc(100dvh - 48px));
  border-radius: 24px;
}
body.widget-mode .brand-tag { display: none; }
body.widget-mode .log { padding: 20px 18px 8px; }
body.widget-mode .composer { padding-left: 12px; padding-right: 12px; }
body.widget-mode .welcome h2 { font-size: clamp(28px, 7vw, 36px); }
body.widget-mode.is-minimized .chat-shell {
  opacity: 0; visibility: hidden; pointer-events: none;
  transform: translateY(12px) scale(.98);
}
.launcher {
  position: fixed; right: 24px; bottom: 24px; z-index: 50;
  display: none; align-items: center; gap: 10px;
  padding: 8px 14px 8px 8px;
  border: 1px solid var(--border-strong); border-radius: 999px;
  background: var(--surface-2); color: var(--text);
  box-shadow: 0 20px 50px -20px rgba(0, 0, 0, .7);
  transition: transform .18s ease, border-color .18s ease;
}
body.widget-mode.is-minimized .launcher { display: flex; animation: rise .2s ease-out both; }
.launcher:hover { transform: translateY(-2px); border-color: var(--accent-border); }
.launcher-mark {
  display: grid; place-items: center; width: 40px; height: 40px; border-radius: 50%;
  background: linear-gradient(145deg, var(--accent-hover), var(--accent));
  color: var(--accent-ink);
}
.launcher-mark .mark-svg { width: 20px; height: 20px; }
.launcher-copy { display: flex; flex-direction: column; text-align: left; line-height: 1.2; }
.launcher-copy strong { font-family: var(--font-display); font-size: 14px; letter-spacing: -.02em; }
.launcher-copy small { color: var(--text-3); font-size: 10px; }
.launcher-dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--success);
  box-shadow: 0 0 0 4px var(--success-soft);
}

/* ============================================================
   13. MOTION
   ============================================================ */
@keyframes msgIn { from { opacity: 0; transform: translateY(9px) scale(.995); } to { opacity: 1; transform: none; } }
@keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes chipIn { from { opacity: 0; transform: translateY(6px) scale(.98); } to { opacity: 1; transform: none; } }
@keyframes replyIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 var(--success-ring); }
  70% { box-shadow: 0 0 0 6px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
}
@keyframes pack {
  0%, 100% { transform: translateY(0) rotate(0); opacity: .55; }
  40% { transform: translateY(-7px) rotate(-8deg); opacity: 1; }
  70% { transform: translateY(0) rotate(4deg); opacity: .85; }
}
@keyframes blink { 0%, 100% { opacity: .25; } 50% { opacity: 1; } }
@keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
@keyframes spin { to { transform: rotate(360deg); } }

/* ============================================================
   14. RESPONSIVE
   ============================================================ */
@media (max-width: 900px) {
  .crop, .dieline { display: none; }
}
@media (max-width: 640px) {
  .wrap { padding: 0; }
  .chat-shell {
    width: 100%; height: 100vh; height: 100dvh;
    border: 0; border-radius: 0; box-shadow: none;
  }
  .app-header { gap: 10px; padding: 13px 14px; }
  .brand { gap: 10px; }
  .brand-mark { width: 40px; height: 40px; flex-basis: 40px; }
  .brand-mark .mark-svg { width: 21px; height: 21px; }
  .brand-name { font-size: 20px; }
  .brand-tag, .response-hint { display: none; }
  .brand-status { margin-top: 5px; }
  .new-chat { width: 36px; padding: 0; background: transparent; border-color: transparent; }
  .new-chat-label { display: none; }
  .icon-btn { height: 36px; min-width: 36px; padding: 0 8px; }
  .log { padding: 20px 14px 8px; }
  .welcome { max-width: 100%; margin-top: 8px; }
  .welcome h2 { font-size: clamp(31px, 9.2vw, 40px); }
  .welcome p { font-size: 14px; }
  .starters { gap: 8px; }
  .starter { min-height: 58px; gap: 9px; padding: 9px; }
  .starter-ico { width: 34px; height: 34px; flex-basis: 34px; }
  .starter-copy strong { font-size: 12px; }
  .starter-copy small { font-size: 10px; }
  .msg-stack { max-width: 88%; }
  .row.me .msg-stack { max-width: 84%; }
  .chips { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; padding-bottom: 2px; margin-right: -16px; }
  .chips::-webkit-scrollbar { display: none; }
  .chip { flex: 0 0 auto; }
  .chip-label { max-width: 180px; }
  .composer { padding: 8px 10px calc(8px + env(safe-area-inset-bottom)); }
  #q { font-size: 16px; }
  .key-hint { display: none; }
  .note { margin-top: 7px; font-size: 10px; }
  .toast { bottom: calc(94px + env(safe-area-inset-bottom)); }
  .scroll-btn { bottom: 8px; }
  body.widget-mode .wrap { padding: 0; }
  body.widget-mode .chat-shell { width: 100vw; height: 100dvh; border-radius: 0; }
}
@media (max-width: 370px) {
  .starters { grid-template-columns: 1fr; }
  .status-sep { display: none; }
  .note span:first-of-type { font-size: 9.5px; }
}
@media (max-height: 720px) and (min-width: 641px) {
  .welcome { margin-top: 0; }
  .welcome h2 { font-size: clamp(30px, 4vw, 38px); margin-top: 14px; }
  .welcome-rule { margin-top: 18px; }
  .log { padding-top: 20px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
    scroll-behavior: auto !important;
  }
  .welcome, .row, .chip, .starter { opacity: 1 !important; transform: none !important; }
}
</style>
</head>
<body>
<div class="ambient" aria-hidden="true">
  <span class="orb orb-a"></span>
  <span class="orb orb-b"></span>
  <span class="grid"></span>
  <span class="dieline d1"></span>
  <span class="dieline d2"></span>
  <span class="grain"></span>
  <span class="crop tl"></span><span class="crop tr"></span>
  <span class="crop bl"></span><span class="crop br"></span>
</div>

<div class="wrap">
  <div class="chat-shell" id="chatShell">
    <header class="app-header">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">
          <svg class="mark-svg" viewBox="0 0 24 24"><use href="#i-carton"></use></svg>
        </div>
        <div class="brand-copy">
          <div class="brand-line">
            <h1 class="brand-name">Print<span>247</span></h1>
            <span class="brand-tag">Packaging studio</span>
          </div>
          <div class="brand-status">
            <span class="status"><span class="dot pulse" aria-hidden="true"></span>Online</span>
            <span class="status-sep" aria-hidden="true"></span>
            <span class="response-hint">Usually replies in a few minutes</span>
          </div>
        </div>
      </div>
      <div class="header-actions">
        <button class="icon-btn new-chat" type="button" onclick="newChat()" aria-label="Start a new chat" title="New chat" data-tip="New chat">
          <svg class="icon" aria-hidden="true"><use href="#i-compose"></use></svg>
          <span class="new-chat-label">New chat</span>
        </button>
        <button class="icon-btn" type="button" id="themeToggle" onclick="toggleTheme()" aria-label="Switch to light mode" title="Switch to light mode" data-tip="Theme">
          <svg class="icon icon-sun" aria-hidden="true"><use href="#i-sun"></use></svg>
          <svg class="icon icon-moon" aria-hidden="true"><use href="#i-moon"></use></svg>
        </button>
        <button class="icon-btn widget-only" type="button" onclick="minimizeChat()" aria-label="Minimize chat" title="Minimize chat" data-tip="Minimize">
          <svg class="icon" aria-hidden="true"><use href="#i-minus"></use></svg>
        </button>
      </div>
    </header>

    <div class="chat-body">
      <div class="log-wrap">
        <div id="log" class="log" role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation with Print247" tabindex="0"></div>
        <button id="scrollBtn" class="scroll-btn" type="button" onclick="jumpToLatest()" aria-label="Scroll to latest messages">
          <svg class="icon" aria-hidden="true"><use href="#i-down"></use></svg>
          <span class="scroll-badge" id="unreadBadge" hidden>1</span>
        </button>
      </div>

      <div class="composer">
        <div id="replybar" role="group" aria-label="Replying to a previous message">
          <span class="replybar-ico" aria-hidden="true"><svg class="icon"><use href="#i-reply"></use></svg></span>
          <div class="replybar-copy">
            <span class="replybar-label">Replying to</span>
            <span id="replytext"></span>
          </div>
          <button type="button" class="replybar-close" onclick="cancelReply()" aria-label="Cancel reply">
            <svg class="icon" aria-hidden="true"><use href="#i-close"></use></svg>
          </button>
        </div>

        <form class="composer-form" onsubmit="return send(event)" autocomplete="off">
          <button type="button" class="composer-btn attach-btn" onclick="pickDesignFile()" aria-label="Attach design file" title="Attach design file">
            <svg class="icon" aria-hidden="true"><use href="#i-clip"></use></svg>
          </button>
          <input type="file" id="designFileInput" hidden accept=".png,.jpg,.jpeg,.webp,.pdf,.ai,.eps,.zip" onchange="uploadDesign(this.files[0]); this.value = '';">
          <label class="sr-only" for="q">Message Print247</label>
          <textarea id="q" name="message" rows="1" placeholder="Tell us what you're packing…" enterkeyhint="send" autocomplete="off" autocapitalize="sentences" spellcheck="true"></textarea>
          <button class="send" id="sendBtn" type="submit" aria-label="Send message" disabled>
            <svg class="icon send-icon" aria-hidden="true"><use href="#i-up"></use></svg>
            <span class="send-spinner" aria-hidden="true"></span>
          </button>
        </form>

        <p class="note">
          <svg class="icon note-icon" aria-hidden="true"><use href="#i-info"></use></svg>
          <span>Prices depend on your exact spec — we’ll collect it and point you to a quote.</span>
          <span class="key-hint" aria-hidden="true"><kbd>Enter</kbd> to send</span>
        </p>
      </div>
    </div>
    <div id="toast" class="toast" role="status" aria-live="polite" hidden></div>
  </div>
</div>

<button class="launcher" id="launcher" type="button" onclick="openChat()" aria-label="Open Print247 chat">
  <span class="launcher-mark" aria-hidden="true"><svg class="mark-svg" viewBox="0 0 24 24"><use href="#i-carton"></use></svg></span>
  <span class="launcher-copy"><strong>Print247</strong><small>Chat with the studio</small></span>
  <span class="launcher-dot" aria-hidden="true"></span>
</button>

<svg class="svg-sprite" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
  <symbol id="i-carton" viewBox="0 0 24 24">
    <path d="M12 2.8 20.4 7.4v9.2L12 21.2 3.6 16.6V7.4L12 2.8Z"/>
    <path d="m3.6 7.4 8.4 4.8 8.4-4.8M12 12.2v9"/>
    <path d="m7.7 5.1 8.5 4.9"/>
  </symbol>
  <symbol id="i-bag" viewBox="0 0 24 24">
    <path d="M7.2 8.2h9.6l1.2 12.1H6L7.2 8.2Z"/>
    <path d="M8.4 8.2V5.4h7.2v2.8M9.7 5.4V3.4h4.6v2"/>
    <path d="M9.2 12.1h5.6"/>
  </symbol>
  <symbol id="i-label" viewBox="0 0 24 24">
    <path d="M4 6.2h8.8L20 12.5l-7.2 7.2L4 12.2V6.2Z"/>
    <circle cx="8.2" cy="10" r="1.3"/>
  </symbol>
  <symbol id="i-truck" viewBox="0 0 24 24">
    <path d="M3 6.8h10.4v9.4H3zM13.4 10h4l3.2 3.2v3H13.4"/>
    <circle cx="6.6" cy="18.2" r="1.7"/><circle cx="17.1" cy="18.2" r="1.7"/>
    <path d="M8.3 18.2h7.1"/>
  </symbol>
  <symbol id="i-ruler" viewBox="0 0 24 24">
    <path d="m3.8 16.8 13-13 3.4 3.4-13 13-3.4-3.4Z"/>
    <path d="m7.2 13.4 2 2M9.9 10.7l1.3 1.3M12.4 8.2l2 2M15.1 5.5l1.3 1.3"/>
  </symbol>
  <symbol id="i-layers" viewBox="0 0 24 24">
    <path d="m12 3 8 4.3-8 4.3-8-4.3L12 3Z"/>
    <path d="m4 12 8 4.3 8-4.3M4 16.4l8 4.3 8-4.3"/>
  </symbol>
  <symbol id="i-image" viewBox="0 0 24 24">
    <rect x="3.2" y="4.2" width="17.6" height="15.6" rx="2.2"/>
    <circle cx="8.8" cy="9.4" r="1.5"/>
    <path d="m4.5 17.2 4.8-4.7 3.2 3 2.3-2.2 4.7 4.6"/>
  </symbol>
  <symbol id="i-tag" viewBox="0 0 24 24">
    <path d="M4 5h8.4L20 12.6 12.6 20 4 11.4V5Z"/>
    <circle cx="8.2" cy="8.8" r="1.2"/>
    <path d="m12.2 10.8 2.6 2.6"/>
  </symbol>
  <symbol id="i-arrow-right" viewBox="0 0 24 24"><path d="M4 12h15M13 6l6 6-6 6"/></symbol>
  <symbol id="i-down" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></symbol>
  <symbol id="i-up" viewBox="0 0 24 24"><path d="M12 19V5M6 11l6-6 6 6"/></symbol>
  <symbol id="i-compose" viewBox="0 0 24 24">
    <path d="M4 20h4l10.2-10.2-4-4L4 16v4Z"/>
    <path d="m13.4 6.6 4 4M14.2 3.4h6.4v6.4"/>
  </symbol>
  <symbol id="i-sun" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="4"/>
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>
  </symbol>
  <symbol id="i-moon" viewBox="0 0 24 24"><path d="M20.2 15.1A8.4 8.4 0 0 1 8.9 3.8 8.5 8.5 0 1 0 20.2 15.1Z"/></symbol>
  <symbol id="i-minus" viewBox="0 0 24 24"><path d="M5 12h14"/></symbol>
  <symbol id="i-close" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></symbol>
  <symbol id="i-reply" viewBox="0 0 24 24"><path d="M9 7 4 12l5 5M4 12h9.5A5.5 5.5 0 0 1 19 17.5V19"/></symbol>
  <symbol id="i-info" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="8.6"/>
    <path d="M12 11v5M12 8h.01"/>
  </symbol>
  <symbol id="i-clip" viewBox="0 0 24 24">
    <path d="m9.5 12.5 4.7-4.7a3.1 3.1 0 0 1 4.4 4.4l-6.9 6.9a5.2 5.2 0 0 1-7.4-7.4l7-7"/>
  </symbol>
  <symbol id="i-doc" viewBox="0 0 24 24">
    <path d="M6 3.5h8l4 4v13H6v-17Z"/><path d="M14 3.5v4h4M9 12h6M9 15h6"/>
  </symbol>
  <symbol id="i-copy" viewBox="0 0 24 24">
    <rect x="8" y="8" width="11" height="11" rx="1.8"/>
    <path d="M16 8V5.8A1.8 1.8 0 0 0 14.2 4H5.8A1.8 1.8 0 0 0 4 5.8v8.4A1.8 1.8 0 0 0 5.8 16H8"/>
  </symbol>
  <symbol id="i-alert" viewBox="0 0 24 24">
    <path d="M12 3.8 21 20H3L12 3.8Z"/><path d="M12 9v4.5M12 17h.01"/>
  </symbol>
  <symbol id="i-retry" viewBox="0 0 24 24"><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 9A7 7 0 0 1 18.7 7.3L20 12M4 12l1.3 4.7A7 7 0 0 0 17.9 15"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24"><path d="m5 12.5 4.4 4.4L19 7"/></symbol>
  <symbol id="i-spark" viewBox="0 0 24 24"><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z"/></symbol>
</svg>

<!--
  Reusable rich-message markup for a future structured-response renderer.
  These templates stay inert because /chat currently returns text and slots;
  no new quote, selection or artwork-upload flow is introduced here.
-->
<template data-p247-template="product-card">
  <article class="product-card">
    <div class="product-media" aria-hidden="true"><svg class="icon"><use href="#i-carton"></use></svg></div>
    <div class="product-body">
      <h3 class="product-title" data-slot="title">Custom packaging</h3>
      <span class="product-meta" data-slot="minimum">MOQ from 1,000 units</span>
      <button type="button" class="product-cta" disabled>Get quote</button>
    </div>
  </article>
</template>

<template data-p247-template="option-selector">
  <fieldset class="option-group">
    <legend class="option-label" data-slot="label">Choose a size</legend>
    <div class="option-list">
      <label class="option"><input class="option-input" type="radio" name="p247-size" value="small"><span class="option-dot" aria-hidden="true"></span><span data-slot="option">Small</span></label>
      <label class="option"><input class="option-input" type="radio" name="p247-size" value="medium"><span class="option-dot" aria-hidden="true"></span><span data-slot="option">Medium</span></label>
      <label class="option"><input class="option-input" type="radio" name="p247-size" value="large"><span class="option-dot" aria-hidden="true"></span><span data-slot="option">Large</span></label>
    </div>
  </fieldset>
</template>

<template data-p247-template="artwork-dropzone">
  <div class="dropzone" role="group" aria-disabled="true" aria-label="Artwork upload">
    <svg class="icon" aria-hidden="true"><use href="#i-image"></use></svg>
    <strong>Artwork upload</strong>
    <small>PDF, AI, PNG or JPG · up to 10MB</small>
  </div>
</template>

<script>
/* ============================================================
   CONTRACTS KEPT FROM THE OLD WIDGET
   ids: log, q, sendBtn, replybar, replytext, typing
   fns: send, newChat, quick, setReply, cancelReply, greet,
        addBot, addMe, typingRow
   storage: p247_session, p247_chat_<session>
   API: POST /chat, GET /api/chat/history (unchanged payloads)
   ============================================================ */
const log = document.getElementById('log');
const q = document.getElementById('q');
const btn = document.getElementById('sendBtn');
const chatShell = document.getElementById('chatShell');
const scrollBtn = document.getElementById('scrollBtn');
const unreadBadge = document.getElementById('unreadBadge');
const themeToggle = document.getElementById('themeToggle');
const themeMeta = document.getElementById('themeColor');
const toastEl = document.getElementById('toast');

// Session ids must be unique per visitor from the FIRST load: the
// old 'web-ui' fallback gave every first-time visitor (and every
// localStorage-blocked browser) the SAME id, so their Mongo slots
// and history collided. A stored 'web-ui' from the old code is
// migrated to a fresh id on sight (Oct 30 audit, Priority 0).
function createSessionId() { return crypto.randomUUID ? crypto.randomUUID() : ('p247-' + Date.now() + '-' + Math.random().toString(36).slice(2)); }
let sessionId;
try { sessionId = localStorage.getItem('p247_session'); if (!sessionId || sessionId === 'web-ui') { sessionId = createSessionId(); localStorage.setItem('p247_session', sessionId); } }
catch (e) { sessionId = createSessionId(); }
// Sales-rep persona: the exact 10 human rep names from the old-chats
// JSON (repName field, 32,469 chats). 'Support Ecommerce' (1 chat)
// is a generic account, not a person, so it is excluded. The rep is
// picked per session (hash of sessionId), so a refresh keeps the
// same rep and a New chat can get another — like the old bot,
// where each chat belonged to one rep.
const REP_NAMES = ['Frank Castle', 'Jessica Joe', 'Alex Kane', 'Max Carter', 'Harry Brook', 'Ethan Wilson', 'Paul Smith', 'Brian Tylar', 'Hazel Grace', 'Nancy Wilson'];
function repName() { let h = 0; for (const ch of sessionId) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return REP_NAMES[h % REP_NAMES.length]; }
let pendingReply = null;
let busy = false;
let unread = 0;
let requestToken = 0;
let toastTimer = null;

/* ---------- small helpers ---------- */
const icon = (name, cls) => `<svg class="icon ${cls || ''}" aria-hidden="true"><use href="#${name}"></use></svg>`;
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
/* JSON string encoded for a double-quoted HTML attribute (quotes become entities). */
const jsArg = (v) => esc(JSON.stringify(v));
const titleCase = (s) => String(s || '').replace(/(^|\s)\S/g, c => c.toUpperCase());
const timeNow = () => { try { return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date()); } catch (e) { return ''; } };
const reduceMotion = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---------- markdown-lite renderer (escape first, then format) ---------- */
function fmt(src) {
  const tokens = [];
  const save = (html, block) => {
    const i = tokens.length;
    tokens.push(html);
    return (block ? '\u0002b' : '\u0001i') + i + (block ? '\u0002' : '\u0001');
  };
  let t = esc(src).replace(/\r\n?/g, '\n');

  t = t.replace(/```[^\n]*\n?([\s\S]*?)```/g, (m, code) =>
    save('<pre class="code-block"><code>' + code.replace(/\n$/, '') + '</code></pre>', true));
  t = t.replace(/`([^`\n]+)`/g, (m, code) => save('<code>' + code + '</code>', false));
  t = t.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, (m, label, url) =>
    save('<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + label + '</a>', false));
  t = t.replace(/(^|[\s(])(https?:\/\/[^\s<)]+[^\s<).,;:!?])/g, (m, pre, url) =>
    pre + save('<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + '</a>', false));

  t = t.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s.,!?)]|$)/g, '$1<em>$2</em>');
  t = t.replace(/\u0001i(\d+)\u0001/g, (m, i) => tokens[+i]);

  const out = [];
  let para = [];
  let list = null;
  const flushPara = () => { if (para.length) { out.push('<p>' + para.join('<br>') + '</p>'); para = []; } };
  const flushList = () => {
    if (!list) return;
    out.push('<' + list.type + '>' + list.items.map(x => '<li>' + x + '</li>').join('') + '</' + list.type + '>');
    list = null;
  };

  t.split('\n').forEach(line => {
    if (!line.trim()) { flushPara(); flushList(); return; }
    const blockToken = line.match(/^\u0002b(\d+)\u0002$/);
    if (blockToken) { flushPara(); flushList(); out.push(tokens[+blockToken[1]]); return; }
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    if (bullet) {
      flushPara();
      if (!list || list.type !== 'ul') { flushList(); list = { type: 'ul', items: [] }; }
      list.items.push(bullet[1]);
      return;
    }
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (numbered) {
      flushPara();
      if (!list || list.type !== 'ol') { flushList(); list = { type: 'ol', items: [] }; }
      list.items.push(numbered[1]);
      return;
    }
    const heading = line.match(/^\s*#{1,3}\s+(.*)$/);
    if (heading) { flushPara(); flushList(); out.push('<h4>' + heading[1] + '</h4>'); return; }
    flushList();
    para.push(line);
  });
  flushPara();
  flushList();
  return out.join('') || '';
}

/* ---------- scroll / unread ---------- */
function nearBottom() { return log.scrollHeight - log.scrollTop - log.clientHeight < 80; }
function scrollLatest(behavior) {
  log.scrollTo({ top: log.scrollHeight, behavior: reduceMotion() ? 'auto' : (behavior || 'smooth') });
}
function resetUnread() {
  unread = 0;
  unreadBadge.hidden = true;
  scrollBtn.classList.remove('show');
  scrollBtn.setAttribute('aria-label', 'Scroll to latest messages');
}
function bumpUnread() {
  unread += 1;
  unreadBadge.textContent = unread > 9 ? '9+' : String(unread);
  unreadBadge.hidden = false;
  scrollBtn.classList.add('show');
  scrollBtn.setAttribute('aria-label', 'Scroll to latest, ' + unread + ' new message' + (unread > 1 ? 's' : ''));
}
function syncScrollButton() {
  if (nearBottom()) resetUnread();
  else scrollBtn.classList.add('show');
}
function jumpToLatest() {
  scrollLatest();
  resetUnread();
  log.focus({ preventScroll: true });
}
log.addEventListener('scroll', syncScrollButton, { passive: true });

/* ---------- save / restore local backup ---------- */
function saveLocal() {
  try {
    /* Keep only conversational markup: no transient typing, hero, skeleton or errors. */
    const clean = log.cloneNode(true);
    clean.querySelectorAll('.error-row, #typing, .skeleton, .welcome').forEach(n => n.remove());
    localStorage.setItem('p247_chat_' + sessionId, clean.innerHTML);
  } catch (e) {}
}
function restoreLocal() {
  try {
    const h = localStorage.getItem('p247_chat_' + sessionId);
    if (h) {
      log.innerHTML = h;
      requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; resetUnread(); });
      return true;
    }
  } catch (e) {}
  return false;
}

/* ---------- message helpers ---------- */
function lastSender() {
  const rows = log.querySelectorAll('.row');
  if (!rows.length) return null;
  return rows[rows.length - 1].classList.contains('me') ? 'me' : 'bot';
}
function insert(html, forceScroll) {
  const wasNear = nearBottom();
  log.insertAdjacentHTML('beforeend', html);
  if (wasNear || forceScroll) {
    requestAnimationFrame(() => { scrollLatest(wasNear ? 'smooth' : 'auto'); resetUnread(); });
  } else {
    bumpUnread();
  }
  saveLocal();
}
function avatarHTML() {
  return `<div class="avatar" aria-hidden="true"><svg class="mark-svg" viewBox="0 0 24 24"><use href="#i-carton"></use></svg></div>`;
}
function stampHTML(stamp) {
  return stamp ? `<time class="stamp">${esc(stamp)}</time>` : '';
}
function sourcesHTML(sources) {
  if (!sources || !sources.length) return '';
  const items = sources.map(s => {
    const safe = esc(s);
    const isUrl = /^https?:\/\//i.test(s);
    return isUrl
      ? `<a class="src-item" href="${safe}" target="_blank" rel="noopener noreferrer" title="${safe}">${icon('i-doc')}${safe}</a>`
      : `<span class="src-item" title="${safe}">${icon('i-doc')}${safe}</span>`;
  }).join('');
  return `<div class="src"><span class="src-label">Sources</span>${items}</div>`;
}
function iconFor(text) {
  const t = String(text).toLowerCase();
  if (/mylar|bag|pouch/.test(t)) return 'i-bag';
  if (/label|sticker/.test(t)) return 'i-label';
  if (/ship|deliver|free|refund|return/.test(t)) return 'i-truck';
  if (/box|carton|mailer/.test(t)) return 'i-carton';
  if (/size|inch|mm|cm|\d+\s*x\s*\d+/.test(t)) return 'i-ruler';
  if (/artwork|file|design|image/.test(t)) return 'i-image';
  if (/price|quote|cost|minimum|moq|ship/.test(t)) return 'i-tag';
  if (/\d|quantity|units|more than|not sure about q/.test(t)) return 'i-layers';
  if (/change/.test(t)) return 'i-retry';
  return 'i-arrow-right';
}
function chipsHTML(sugs) {
  if (!sugs || !sugs.length) return '';
  return '<div class="chips" role="group" aria-label="Suggested replies">' + sugs.map((s, i) =>
    `<button type="button" class="chip" style="--i:${i}" onclick="quick(${jsArg(s)})">` +
    `<span class="chip-ico" aria-hidden="true">${icon(iconFor(s))}</span>` +
    `<span class="chip-label">${esc(s)}</span>` +
    `${icon('i-arrow-right', 'chip-arrow')}` +
    '</button>'
  ).join('') + '</div>';
}
function quoteCard(slots) {
  const rows = [];
  const add = (label, value) => {
    if (value !== undefined && value !== null && String(value).trim() && String(value).toLowerCase() !== 'none') {
      rows.push([label, String(value)]);
    }
  };
  add('Product', titleCase(slots.product));
  add('Size', slots.sizes);
  if (slots.quantity) {
    add('Quantity', /^\d+$/.test(String(slots.quantity))
      ? Number(slots.quantity).toLocaleString() + ' units'
      : slots.quantity);
  }
  add('Material', titleCase(slots.material));
  add('Finish', titleCase(slots.finishes));
  add('Extras', titleCase(slots.extras));
  if (slots.skus && String(slots.skus) !== '1') add('SKUs', slots.skus);
  if (!rows.length) return '';

  const plain = rows.map(([label, value]) => label + ': ' + value).join('\n');
  return `<div class="quote-card" aria-label="Quote summary">` +
    `<div class="quote-head"><span class="quote-kicker">${icon('i-check')}Spec brief</span>` +
    `<span class="quote-status">Ready for pricing</span></div>` +
    `<div class="quote-rows">` + rows.map(([label, value]) =>
      `<div class="quote-row"><span class="q-label">${esc(label)}</span><span class="q-value">${esc(value)}</span></div>`
    ).join('') + `</div>` +
    `<div class="quote-foot"><span class="quote-note">A team member will confirm price and turnaround.</span>` +
    `<button type="button" class="quote-copy" onclick="copySpec(this)" data-copy="${esc(plain).replace(/\n/g, '&#10;')}">${icon('i-copy')}<span>Copy brief</span></button></div>` +
    `</div>`;
}

/* ---------- existing render API (signatures kept, extra args optional) ---------- */
function addBot(text, sugs, sources, stamp, meta) {
  if (stamp === undefined) stamp = timeNow();
  const grouped = lastSender() === 'bot' ? ' grouped' : '';
  const card = meta && meta.handoff === 'complete' && meta.slots ? quoteCard(meta.slots) : '';
  const html = `<div class="row bot${grouped}">` + avatarHTML() +
    `<div class="msg-stack"><div class="bubble">${fmt(text)}</div>${card}` +
    `<div class="msg-meta">${stampHTML(stamp)}` +
    `<button type="button" class="replybtn" onclick="setReply(${jsArg(text)})" aria-label="Reply to this message">${icon('i-reply')}Reply</button></div>` +
    `${chipsHTML(sugs)}${sourcesHTML(sources)}</div></div>`;
  insert(html, false);
}
function addMe(t, quote, stamp) {
  if (stamp === undefined) stamp = timeNow();
  const grouped = lastSender() === 'me' ? ' grouped' : '';
  const quoted = quote
    ? `<div class="quote"><span class="quote-label">Replying to</span>${esc(quote)}</div>`
    : '';
  const html = `<div class="row me${grouped}"><div class="msg-stack">` +
    `<div class="bubble">${quoted}${esc(t)}</div>` +
    `<div class="msg-meta">${stampHTML(stamp)}</div></div></div>`;
  insert(html, true);
}
function typingRow() {
  removeTyping();
  const html = `<div class="row bot" id="typing">` + avatarHTML() +
    `<div class="msg-stack"><div class="bubble typing" role="status">` +
    `<div class="typing-boxes" aria-hidden="true"><i></i><i></i><i></i></div>` +
    `<div class="typing-copy"><span class="typing-label">Print247 is typing</span><span class="typing-sub">Packing your answer</span></div>` +
    `</div></div></div>`;
  const wasNear = nearBottom();
  log.insertAdjacentHTML('beforeend', html);
  if (wasNear) requestAnimationFrame(() => scrollLatest());
}
function removeTyping() {
  const el = document.getElementById('typing');
  if (el) el.remove();
}
function addError(text, quote, row) {
  if (row) row.remove();
  const grouped = lastSender() === 'bot' ? ' grouped' : '';
  const html = `<div class="row bot error-row${grouped}" role="alert">` + avatarHTML() +
    `<div class="msg-stack"><div class="bubble error-bubble">${icon('i-alert', 'error-icon')}` +
    `<div class="error-copy"><strong>Message didn’t send.</strong><span>Check your connection and try again.</span></div>` +
    `<button type="button" class="retry-btn" onclick="retrySend(this, ${jsArg(text)}, ${jsArg(quote)})">${icon('i-retry')}Retry</button>` +
    `</div></div></div>`;
  insert(html, true);
}

/* ---------- send flow (same endpoint + payload) ---------- */
async function deliver(text, quote, token) {
  try {
    const r = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, session_id: sessionId, reply_to: quote })
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    if (token !== requestToken) return;
    removeTyping();
    addBot(d.reply, d.suggestions || [], d.sources || [], undefined, d);
  } catch (err) {
    if (token !== requestToken) return;
    removeTyping();
    addError(text, quote);
  } finally {
    if (token === requestToken) {
      busy = false;
      syncSendState();
      q.focus();
    }
  }
}
async function send(e) {
  if (e && e.preventDefault) e.preventDefault();
  const t = q.value.trim();
  if (!t || busy) return false;
  const quote = pendingReply;
  const token = ++requestToken;
  removeWelcome();
  addMe(t, quote);
  q.value = '';
  grow();
  cancelReply();
  busy = true;
  syncSendState();
  typingRow();
  await deliver(t, quote, token);
  return false;
}
async function retrySend(button, text, quote) {
  if (busy) return;
  const token = ++requestToken;
  const row = button.closest('.row');
  if (row) row.remove();
  busy = true;
  syncSendState();
  typingRow();
  await deliver(text, quote, token);
}
function quick(t) {
  q.value = t;
  grow();
  syncSendState();
  send(new Event('submit'));
}

/* ---------- composer ---------- */
function grow() {
  q.style.height = 'auto';
  q.style.height = Math.min(q.scrollHeight, 132) + 'px';
}
function syncSendState() {
  btn.disabled = busy || !q.value.trim();
  btn.setAttribute('aria-busy', busy ? 'true' : 'false');
}
q.addEventListener('input', () => { grow(); syncSendState(); });
q.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    if (!busy && q.value.trim()) send(new Event('submit'));
  }
});
syncSendState();

/* ---------- reply / chips / welcome ---------- */
function setReply(t) {
  pendingReply = t;
  document.getElementById('replytext').textContent = t.slice(0, 120);
  document.getElementById('replybar').style.display = 'flex';
  q.focus();
}
function cancelReply() {
  pendingReply = null;
  document.getElementById('replybar').style.display = 'none';
}
function removeWelcome() {
  const w = log.querySelector('.welcome');
  if (w) w.remove();
}
function collapseChips(group) {
  if (!group || group.classList.contains('is-used')) return;
  group.style.height = group.offsetHeight + 'px';
  group.style.overflow = 'hidden';
  group.classList.add('is-used');
  requestAnimationFrame(() => {
    group.style.height = '0px';
    group.style.marginTop = '0px';
    group.style.paddingTop = '0px';
    group.style.paddingBottom = '0px';
  });
  setTimeout(() => group.remove(), 240);
}
log.addEventListener('click', e => {
  const chip = e.target.closest('.chip');
  if (chip) collapseChips(chip.closest('.chips'));
});

function starter(iconName, title, sub, message, index) {
  return `<button type="button" class="starter" style="--i:${index}" onclick="quick(${jsArg(message)})">` +
    `<span class="starter-ico" aria-hidden="true">${icon(iconName)}</span>` +
    `<span class="starter-copy"><strong>${esc(title)}</strong><small>${esc(sub)}</small></span>` +
    `${icon('i-arrow-right', 'starter-arrow')}</button>`;
}
function greet() {
  log.innerHTML = `<section class="welcome" aria-label="Start a conversation">` +
    `<div class="welcome-kicker">${icon('i-spark')}Print247 concierge</div>` +
    `<h2>What are we <em>packing</em> today?</h2>` +
    `<p>Hi, I’m ${repName().split(' ')[0]} from Print247. Tell me what’s going inside, the size and quantity. I’ll pull the right spec and walk you to a quote — no guesswork.</p>` +
    `<div class="welcome-rule">Pick a starting point</div>` +
    `<div class="starters">` +
      starter('i-bag', 'Mylar bags', 'Barrier bags & pouches', 'I need mylar bags', 0) +
      starter('i-carton', 'Custom boxes', 'Retail & shipping cartons', 'I need custom boxes', 1) +
      starter('i-label', 'Labels', 'Roll labels & stickers', 'I need labels', 2) +
      starter('i-truck', 'Shipping & refunds', 'Ask about delivery or returns', 'Is shipping free?', 3) +
    `</div>` +
    `<div class="welcome-meta"><span class="status"><span class="dot" aria-hidden="true"></span>Online now</span><span class="status-sep" aria-hidden="true"></span><span>No account needed · plain-English spec help</span></div>` +
    `</section>`;
  log.scrollTop = 0;
  resetUnread();
  scrollBtn.classList.remove('show');
}
function newChat() {
  sessionId = createSessionId();
  try { localStorage.setItem('p247_session', sessionId); } catch (e) {}
  requestToken += 1;
  busy = false;
  q.value = '';
  grow();
  cancelReply();
  syncSendState();
  log.innerHTML = '';
  resetUnread();
  greet();
}

/* ---------- quote card copy + toast ---------- */
async function copySpec(button) {
  const text = button.dataset.copy || '';
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (_) {}
    ta.remove();
  }
  const label = button.querySelector('span');
  if (label) {
    const old = label.textContent;
    label.textContent = 'Copied';
    setTimeout(() => { label.textContent = old; }, 1400);
  }
  showToast('Quote brief copied.');
}
function showToast(message) {
  clearTimeout(toastTimer);
  toastEl.textContent = message;
  toastEl.hidden = false;
  requestAnimationFrame(() => toastEl.classList.add('show'));
  toastTimer = setTimeout(() => {
    toastEl.classList.remove('show');
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, 220);
  }, 4200);
}
function pickDesignFile() {
  const inp = document.getElementById('designFileInput');
  if (inp) inp.click();
}
async function uploadDesign(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('session_id', sessionId);
  fd.append('file', file);
  addMe('Design file: ' + file.name);
  try {
    const r = await fetch('/api/chat/upload', { method: 'POST', body: fd });
    const d = await r.json();
    if (!r.ok || !d.ok) throw new Error(d.detail || 'upload failed');
    addBot(d.reply, [], [], undefined, d);
  } catch (err) {
    showToast('Could not upload that file — please try a PNG, JPG, PDF, AI, EPS or ZIP file under 10MB.');
  }
}

/* ---------- theme ---------- */
const THEME_META = { midnight: '#08090a', kraft: '#e9ddca', light: '#eef0ed' };
function currentTheme() { return document.documentElement.dataset.theme || 'midnight'; }
function applyTheme(theme, persist) {
  document.documentElement.dataset.theme = theme;
  themeMeta.setAttribute('content', THEME_META[theme] || THEME_META.midnight);
  const light = theme !== 'midnight';
  const label = light ? 'Switch to dark mode' : 'Switch to light mode';
  themeToggle.setAttribute('aria-label', label);
  themeToggle.title = label;
  if (persist !== false) { try { localStorage.setItem('p247_theme', theme); } catch (e) {} }
}
function toggleTheme() {
  applyTheme(currentTheme() === 'midnight' ? 'kraft' : 'midnight');
}

/* ---------- widget mode ---------- */
function minimizeChat() {
  document.body.classList.add('is-minimized');
  const launcher = document.getElementById('launcher');
  if (launcher) setTimeout(() => launcher.focus(), 60);
}
function openChat() {
  document.body.classList.remove('is-minimized');
  q.focus();
}

/* ---------- loading skeleton ---------- */
function showSkeleton() {
  log.innerHTML = `<div class="skeleton" id="historySkeleton" aria-hidden="true">` +
    `<div class="sk-row"><span class="sk-avatar"></span><div class="sk-lines"><span class="sk-line"></span><span class="sk-line"></span><span class="sk-line"></span></div></div>` +
    `<div class="sk-row me"><div class="sk-lines"><span class="sk-line"></span><span class="sk-line"></span></div></div>` +
    `<div class="sk-row"><span class="sk-avatar"></span><div class="sk-lines"><span class="sk-line"></span><span class="sk-line"></span><span class="sk-line"></span></div></div>` +
    `</div>`;
}

/* ---------- boot: URL presets, widget mode, theme label, history ---------- */
const params = new URLSearchParams(location.search);
if (params.get('widget') === '1') document.body.classList.add('widget-mode');
const urlTheme = params.get('theme');
applyTheme(['midnight', 'kraft', 'light'].includes(urlTheme) ? urlTheme : currentTheme(), false);

showSkeleton();
(async function init() {
  try {
    const r = await fetch('/api/chat/history?session_id=' + encodeURIComponent(sessionId));
    const h = await r.json();
    if (h && h.length) {
      log.innerHTML = '';
      h.forEach(m => {
        if (m.reply_to) addMe(m.message, m.reply_to, null);
        else addMe(m.message, null, null);
        addBot(m.reply, m.suggestions || [], m.sources || [], null, null);
      });
      requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; resetUnread(); });
      return;
    }
  } catch (e) {}
  const sk = document.getElementById('historySkeleton');
  if (sk) sk.remove();
  if (!restoreLocal()) greet();
})();
</script>
</body>
</html>"""
