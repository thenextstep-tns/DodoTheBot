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
   chimneys at map scale is noise rather than detail. */
/* Close-up flourishes stay hidden until the map says we are close. The
   wanderers do not: a town with a zoo in it and nothing alive in it is a shed
   with a fence, and on a small base image a town is never drawn wide enough for
   the close-up gate to open at all. They are always there; only their walking
   waits for close range. */
.fx { display: none; }
.dltown.close .fx { display: inline; }
.walker { display: inline; opacity: .85; }
/* People do not sway on the spot. They walk somewhere, stand about for a while,
   wander back, and stop again, turning to face the way they are going. The
   waiting is in the keyframes, because the pauses are what make it look like
   somebody deciding rather than something oscillating. Four routes and four
   durations, so a town does not look like a chorus line. */
.gait { transform-box: fill-box; transform-origin: bottom center; }
.dltown.close .w1 .gait { animation: dlwalkA 14s ease-in-out infinite; }
.dltown.close .w2 .gait { animation: dlwalkB 19s ease-in-out infinite 3s; }
.dltown.close .w3 .gait { animation: dlwalkA 23s ease-in-out infinite 8s; }
.dltown.close .w4 .gait { animation: dlwalkB 17s ease-in-out infinite 5s; }
@keyframes dlwalkA {
  0%, 12%   { transform: translateX(0) scaleX(1); }
  30%, 46%  { transform: translateX(13px) scaleX(1); }
  50%       { transform: translateX(13px) scaleX(-1); }
  68%, 88%  { transform: translateX(-4px) scaleX(-1); }
  92%, 100% { transform: translateX(0) scaleX(1); }
}
@keyframes dlwalkB {
  0%, 20%   { transform: translateX(0) scaleX(-1); }
  38%       { transform: translateX(-11px) scaleX(-1); }
  44%, 60%  { transform: translateX(-11px) scaleX(1); }
  78%, 94%  { transform: translateX(6px) scaleX(1); }
  100%      { transform: translateX(0) scaleX(1); }
}
@media (prefers-reduced-motion: reduce) {
  .dltown.close .walker .gait { animation: none; }
}
.dltown.close .glow { animation: dlflicker 4s ease-in-out infinite; }
.dltown.close .halo { opacity: .55; animation: dlflicker 3s ease-in-out infinite; }
.dltown.close .pf1 { animation: dlrise 5s linear infinite; }
.dltown.close .pf2 { animation: dlrise 5s linear infinite 1.6s; }
.dltown.close .pf3 { animation: dlrise 5s linear infinite 3.2s; }
.dltown.close .banner { animation: dlwave 2.6s ease-in-out infinite;
  transform-box: fill-box; transform-origin: left center; }
@keyframes dlflicker { 0%,100% { opacity: .85; } 50% { opacity: .45; } }
@keyframes dlrise {
  0% { opacity: 0; transform: translateY(0) scale(.7); }
  25% { opacity: .5; }
  100% { opacity: 0; transform: translateY(-14px) scale(1.4); }
}
@keyframes dlwave { 0%,100% { transform: skewY(0deg); } 50% { transform: skewY(-6deg); } }
@media (prefers-reduced-motion: reduce) {
  .dltown.close .glow, .dltown.close .halo, .dltown.close .pf1,
  .dltown.close .pf2, .dltown.close .pf3, .dltown.close .banner
    { animation: none; }
}

/* Flourish colours the ring the town art draws on its own ground plate. */
.fl1 { --fl1: #ffd682; } .fl2 { --fl2: #ffb84d; } .fl3 { --fl3: #ffc43d; }
.fl4 { --fl4: #78beff; } .fl5 { --fl5: #9682ff; } .fl6 { --fl6: #ff8cd2; }
/* Animated on the flourish ring alone, and by opacity rather than a filter:
   filtering a whole town rasterises it and the highest-tier settlements were
   the ones that blurred first. */
.fl5 ellipse:first-of-type, .fl6 ellipse:first-of-type {
  animation: dlglow 3s ease-in-out infinite; }
@keyframes dlglow { 0%,100% { opacity: .85; } 50% { opacity: .35; } }
@media (prefers-reduced-motion: reduce) {
  .fl5 ellipse:first-of-type, .fl6 ellipse:first-of-type { animation: none; } }

/* A town's own picture, flown as a flag over whatever it has built highest —
   and shown as the same cloth wherever else it appears, so it reads as the
   town's banner in both places rather than as a photograph in one and a flag
   in the other. */
.townflag .cloth { transform-box: fill-box; transform-origin: left center; }
.dltown.close .townflag .cloth { animation: dlwave 3.4s ease-in-out infinite; }
.cardflag { margin-top: 10px; overflow: hidden; border-radius: 8px;
  border: 1px solid var(--edge); }
.cardflag img { display: block; width: 100%; transform-origin: left center;
  animation: dlcloth 5s ease-in-out infinite; }
@keyframes dlcloth {
  0%, 100% { transform: perspective(300px) rotateY(0deg) skewY(0deg); }
  50% { transform: perspective(300px) rotateY(-6deg) skewY(-1.2deg); }
}
@media (prefers-reduced-motion: reduce) {
  .cardflag img, .dltown.close .townflag .cloth { animation: none; }
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
