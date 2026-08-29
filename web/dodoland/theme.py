"""
The look DodoLand's own pages share.

The map page and the player pages are not part of the control panel and do not
wear its chrome. They are the world, so they get the world's palette — paper,
ink and lantern light — rather than the admin stylesheet, and they are
full-window rather than a section inside a settings layout.

This module exists so there is exactly one copy of that palette. It was written
twice within a day of the player pages starting, and two copies of a colour
scheme is two colour schemes as soon as one of them is edited.

Nothing here loads anything. No webfont, no CDN, no icon set: DodoLand draws its
own emblems and inhabitants for the reason written up in ``docs/DODOLAND.md`` —
a font that fails to apply fails silently, at a distance, in exactly the part
people are meant to be looking at.
"""

from __future__ import annotations

import html

PALETTE = """
:root {
  --paper: #f3e5cb; --deep: #e0cba6; --ink: #3b2a1a; --soft: #6d5842;
  --edge: #c8ad83; --lantern: #b9762a; --bar: #241d18;
}
@media (prefers-color-scheme: dark) {
  :root { --paper: #241d18; --deep: #171310; --ink: #efdcc0; --soft: #b39d81;
          --edge: #4a3a2b; --lantern: #f0a64f; --bar: #120f0c; }
}
"""

# The bar across the top of every DodoLand page, and the ghost button in it.
CHROME = """
* { box-sizing: border-box; }
body { margin: 0; background: var(--deep); color: var(--ink);
  font: 15px/1.5 "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif; }
.dlbar { position: sticky; top: 0; height: 52px; z-index: 30;
  display: flex; align-items: center; gap: 14px; padding: 0 16px;
  background: var(--bar); color: #f4e6cf; box-shadow: 0 2px 12px rgba(0,0,0,.4); }
.dlbar a { color: #f0c98a; text-decoration: none; }
.dlbar a:hover { text-decoration: underline; }
.dlspacer { flex: 1 1 auto; }
.dlghost { background: none; border: 1px solid rgba(255,255,255,.25);
  color: inherit; border-radius: 8px; padding: 6px 12px; cursor: pointer;
  font: inherit; font-size: 13px; text-decoration: none; }
.dlghost:hover { background: rgba(255,255,255,.1); text-decoration: none; }
"""


# --------------------------------------------------------------------------- #
#  The artwork's own rules
# --------------------------------------------------------------------------- #
# Everything that makes a drawn town *move*, and the colours flourish paints it
# in. It lives here rather than on the map because the map is no longer the only
# place a town is drawn: a player's own town page draws the same artwork at the
# size of a picture rather than the size of a village.
#
# Two things it depends on and must keep depending on:
#
# * The artwork is wrapped in an element with ``dltown``, and the close-up
#   flourishes wake when that element also has ``close``. On the map that class
#   is toggled by zoom; on a page showing one town it is simply always there.
# * Nothing here uses a CSS ``filter``, and nothing sets ``will-change``.
#   Either promotes the artwork to a composited layer that the browser
#   rasterises once and then scales, so an SVG stops being vector the moment
#   anybody zooms. Effects are opacity, transform and SVG gradients only.
TOWN_ART_CSS = """
/* Close-up flourishes: smoke, lit windows, waving banners, lantern halos. Off
   until the map says we are close enough, because three hundred smoking
   chimneys at map scale is noise rather than detail. The wanderers do not wait:
   a town with a zoo in it and nothing alive in it is a shed with a fence, and
   on a small base image a town is never drawn wide enough for the close-up gate
   to open at all. They are always there; only their walking waits. */
.fx { display: none; }
.dltown.close .fx { display: inline; }
.walker { display: inline; opacity: .9; }

/* ---- who is walking, and where ----------------------------------------- */
/* Twelve routes, handed out by a hash of the town and the walker's index.
   There used to be two, so every crowd moved like a chorus line: half the town
   stepping right in unison and the other half stepping left. Each route is
   several waypoints with real pauses in them, because the pauses are what make
   it look like somebody deciding rather than something oscillating, and each
   turns to face the way it is going. */
.gait { transform-box: fill-box; transform-origin: bottom center; }
.dltown.close .r1  .gait { animation: dlwalkA 14s ease-in-out infinite; }
.dltown.close .r2  .gait { animation: dlwalkB 19s ease-in-out infinite -3s; }
.dltown.close .r3  .gait { animation: dlwalkC 23s ease-in-out infinite -8s; }
.dltown.close .r4  .gait { animation: dlwalkD 17s ease-in-out infinite -5s; }
.dltown.close .r5  .gait { animation: dlwalkA 21s ease-in-out infinite -11s; }
.dltown.close .r6  .gait { animation: dlwalkC 16s ease-in-out infinite -2s; }
.dltown.close .r7  .gait { animation: dlwalkB 26s ease-in-out infinite -14s; }
.dltown.close .r8  .gait { animation: dlwalkD 13s ease-in-out infinite -6s; }
.dltown.close .r9  .gait { animation: dlwalkC 29s ease-in-out infinite -17s; }
.dltown.close .r10 .gait { animation: dlwalkA 18s ease-in-out infinite -9s; }
.dltown.close .r11 .gait { animation: dlwalkD 24s ease-in-out infinite -20s; }
.dltown.close .r12 .gait { animation: dlwalkB 15s ease-in-out infinite -4s; }
@keyframes dlwalkA {
  0%, 9%    { transform: translate(0,0) scaleX(1); }
  26%       { transform: translate(13px,0) scaleX(1); }
  34%, 41%  { transform: translate(13px,0) scaleX(-1); }
  58%       { transform: translate(-4px,-2px) scaleX(-1); }
  66%, 80%  { transform: translate(-4px,-2px) scaleX(1); }
  94%, 100% { transform: translate(0,0) scaleX(1); }
}
@keyframes dlwalkB {
  0%, 14%   { transform: translate(0,0) scaleX(-1); }
  30%       { transform: translate(-11px,1px) scaleX(-1); }
  38%, 52%  { transform: translate(-11px,1px) scaleX(1); }
  68%       { transform: translate(7px,-1px) scaleX(1); }
  76%, 90%  { transform: translate(7px,-1px) scaleX(-1); }
  100%      { transform: translate(0,0) scaleX(-1); }
}
@keyframes dlwalkC {
  0%, 7%    { transform: translate(0,0) scaleX(1); }
  20%       { transform: translate(6px,-3px) scaleX(1); }
  27%, 33%  { transform: translate(6px,-3px) scaleX(1); }
  48%       { transform: translate(17px,1px) scaleX(1); }
  55%, 62%  { transform: translate(17px,1px) scaleX(-1); }
  84%       { transform: translate(-3px,2px) scaleX(-1); }
  91%, 100% { transform: translate(0,0) scaleX(1); }
}
@keyframes dlwalkD {
  0%, 11%   { transform: translate(0,0) scaleX(-1); }
  24%       { transform: translate(-7px,-2px) scaleX(-1); }
  31%, 44%  { transform: translate(-7px,-2px) scaleX(-1); }
  60%       { transform: translate(-15px,2px) scaleX(-1); }
  67%, 74%  { transform: translate(-15px,2px) scaleX(1); }
  92%, 100% { transform: translate(0,0) scaleX(1); }
}

/* ---- light -------------------------------------------------------------- */
/* Opacity is for light and nothing else. Lit windows, lantern halos, embers.
   It was reaching masonry, ponds, rocks and animals through an unscoped
   `ellipse:first-of-type`, which is why a menagerie's pond blinked. Every rule
   below names the thing it animates. */
.dltown.close .glow { animation: dlflicker 4s ease-in-out infinite; }
.dltown.close .halo { opacity: .55; animation: dlflicker 3s ease-in-out infinite; }
.dltown.close .pf1 { animation: dlrise 5s linear infinite; }
.dltown.close .pf2 { animation: dlrise 5s linear infinite -1.6s; }
.dltown.close .pf3 { animation: dlrise 5s linear infinite -3.2s; }
@keyframes dlflicker { 0%,100% { opacity: .85; } 50% { opacity: .45; } }
@keyframes dlrise {
  0% { opacity: 0; transform: translateY(0) scale(.7); }
  25% { opacity: .5; }
  100% { opacity: 0; transform: translateY(-14px) scale(1.4); }
}

/* Cloth moves by skewing, never by fading. */
.dltown.close .banner { animation: dlwave 2.6s ease-in-out infinite;
  transform-box: fill-box; transform-origin: left center; }
@keyframes dlwave { 0%,100% { transform: skewY(0deg); } 50% { transform: skewY(-6deg); } }

/* ---- particles ---------------------------------------------------------- */
/* The smoke was the one effect that already read well, so the grand tiers use
   more of the same idea rather than more fading: embers off a roof, dust
   drifting over warm ground. Particles move; they do not blink. */
.spark { transform-box: fill-box; transform-origin: center; }
.dltown.close .spark { animation: dlember 4.6s ease-in linear infinite; }
.dltown.close .s1 { animation: dlember 4.6s linear infinite; }
.dltown.close .s2 { animation: dlember 5.4s linear infinite -1.2s; }
.dltown.close .s3 { animation: dlember 6.1s linear infinite -2.4s; }
.dltown.close .s4 { animation: dlember 5.0s linear infinite -3.6s; }
.dltown.close .s5 { animation: dlember 6.8s linear infinite -0.6s; }
@keyframes dlember {
  0%   { opacity: 0; transform: translate(0,0) scale(.5); }
  15%  { opacity: .9; }
  70%  { opacity: .5; }
  100% { opacity: 0; transform: translate(4px,-30px) scale(1.1); }
}
.drift { transform-box: fill-box; transform-origin: center; }
.dltown.close .d1 { animation: dldrift 9s linear infinite; }
.dltown.close .d2 { animation: dldrift 12s linear infinite -4s; }
.dltown.close .d3 { animation: dldrift 15s linear infinite -8s; }
@keyframes dldrift {
  0%   { opacity: 0; transform: translate(-6px,0); }
  20%  { opacity: .55; }
  80%  { opacity: .35; }
  100% { opacity: 0; transform: translate(20px,-6px); }
}

/* ---- things that turn --------------------------------------------------- */
/* Rotation rather than a fade wherever the real object would turn: a mill wheel
   that blinks is a broken mill wheel. */
.wheel, .cog, .orbit, .sunwheel, .flmotes, .flring2 {
  transform-box: fill-box; transform-origin: center; }
.dltown.close .wheel { animation: dlspin 9s linear infinite; }
.dltown.close .cog { animation: dlspin 14s linear infinite reverse; }
.dltown.close .orbit { animation: dlspin 11s linear infinite; }
@keyframes dlspin { to { transform: rotate(360deg); } }

/* ---- the top of the ladder ---------------------------------------------- */
/* Tier six leaves the ground. The markup for this shipped a long time ago and
   there was never a rule for it, so the building sat flat on the plate over a
   shadow that made no sense — the whole reason the climb's last rung read as
   nothing at all. */
.lifted { transform-box: fill-box; transform-origin: bottom center; }
.dltown .lifted { transform: translateY(-9px); }
.dltown.close .lifted { animation: dlhover 6s ease-in-out infinite; }
@keyframes dlhover {
  0%,100% { transform: translateY(-8px); }
  50%     { transform: translateY(-14px); }
}
.dltown.close .bbeam { animation: dlbeam 7s ease-in-out infinite; }
@keyframes dlbeam { 0%,100% { opacity: .30; } 50% { opacity: .62; } }
.bring { transform-box: fill-box; transform-origin: center; }
.dltown.close .bring { animation: dlbreathe 5s ease-in-out infinite; }
@keyframes dlbreathe {
  0%,100% { transform: scale(1); opacity: .75; }
  50%     { transform: scale(1.08); opacity: .45; }
}

/* ---- flourish ----------------------------------------------------------- */
/* What a trial rank does to a whole town. It was one flat ellipse stroke at
   every level from one to six, differing only in width — a highlighter mark
   round a puddle, which is exactly what it looked like. The ring is now drawn
   with a gradient and the levels above it add a slowly turning sun, a
   counter-turning outer ring and motes going round the settlement. */
.dltown.close .sunwheel { animation: dlspin 90s linear infinite; }
.dltown.close .flmotes { animation: dlspin 24s linear infinite reverse; }
.dltown.close .flring2 { animation: dlspin 60s linear infinite; }
.dltown.close .sundisc { animation: dlpulse 8s ease-in-out infinite; }
@keyframes dlpulse { 0%,100% { opacity: .5; } 50% { opacity: .78; } }
/* The ring's own gradient sweeps round it rather than the ring blinking. */
.flring { transform-box: fill-box; transform-origin: center; }
.dltown.close .flring { animation: dlsheen 6s ease-in-out infinite; }
@keyframes dlsheen { 0%,100% { opacity: .8; } 50% { opacity: 1; } }

/* A town's own picture, flown as a flag over whatever it has built highest —
   and shown as the same cloth wherever else it appears, so it reads as the
   town's banner in both places rather than as a photograph in one and a flag
   in the other. */
.townflag .cloth { transform-box: fill-box; transform-origin: left center; }
.dltown.close .townflag .cloth { animation: dlcloth 3.4s ease-in-out infinite; }
.cardflag { margin-top: 10px; overflow: hidden; border-radius: 8px;
  border: 1px solid var(--edge); }
.cardflag img { display: block; width: 100%; transform-origin: left center;
  animation: dlcloth 5s ease-in-out infinite; }
@keyframes dlcloth {
  0%, 100% { transform: perspective(300px) rotateY(0deg) skewY(0deg); }
  50% { transform: perspective(300px) rotateY(-6deg) skewY(-1.2deg); }
}

/* Everything that moves stops when the reader has asked for that. */
@media (prefers-reduced-motion: reduce) {
  .dltown .gait, .dltown .glow, .dltown .halo, .dltown .pf1, .dltown .pf2,
  .dltown .pf3, .dltown .banner, .dltown .spark, .dltown .drift,
  .dltown .wheel, .dltown .cog, .dltown .orbit, .dltown .sunwheel,
  .dltown .flmotes, .dltown .flring2, .dltown .flring, .dltown .sundisc,
  .dltown .lifted, .dltown .bbeam, .dltown .bring,
  .dltown .townflag .cloth, .cardflag img { animation: none; }
}
"""


def e(value) -> str:
    return html.escape(str(value))


def bar(*, back: tuple[str, str] | None, title: str, note: str = "",
        links: str = "") -> str:
    """The top bar: a way back, where you are, and whatever else is on offer."""
    left = (f'<a href="{e(back[0])}">&larr; {e(back[1])}</a>' if back else "")
    return (f'<div class="dlbar">{left}<b>{e(title)}</b>'
            f'<span class="dlnote">{e(note)}</span>'
            f'<span class="dlspacer"></span>{links}</div>')
