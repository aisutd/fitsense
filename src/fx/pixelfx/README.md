# pixelfx (vendored)

The runtime (`core/`) and five effects from [pixelfx](https://github.com/patch-gg/pixelfx) at commit `a841596`,
MIT License (see `LICENSE`). Used by `src/components/PixelFx.jsx` and `src/components/RewardLayer.jsx` for the
reward pop-ups.

- `fx/pickups/collect-burst.js`: the sparkle on the button you pressed
- `fx/ui/coin-collect.js`: the coin fountain for FitCoins
- `fx/ui/combo-counter.js`: the "x5 DAY STREAK" counter
- `fx/ui/confetti.js`: confetti from a 7-day streak on
- `fx/ui/achievement.js`: the badge and level-up toasts

The files are unchanged, so a newer pixelfx can be copied over them. To add another effect, copy it from
`src/fx/<category>/` in pixelfx (and the category's `_lib.js` if it imports one).

Notices from pixelfx: `core/sim.js` and the effects that say so at the top of their file adapt Sprite Fusion's
open-source pixel art VFX (https://www.spritefusion.com/pixel-art-vfx), Copyright (c) 2026 Hugo Duprez, MIT License.
`core/act.js` adapts Hollow Crown (https://github.com/rehan-remade/hollow-crown), Copyright (c) 2026 rehan-remade,
MIT License.
