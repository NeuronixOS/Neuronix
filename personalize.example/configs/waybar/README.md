# Waybar customization

Stock bar lives in `Neuronix/Build/default/configs/waybar/` (CPU % + RAM %;
click either opens `btop` in `foot`).

**Override for your machine:** put `config` / `style.css` here under
`personalize/configs/waybar/`. Merge copies this into `~/configs/waybar` and
`links.json` symlinks it to `~/.config/waybar`.

Icons use Font Awesome (`fonts-font-awesome`): microchip (`\uf2db`) for CPU,
database (`\uf1c0`) for RAM. Requires `btop` (already in default `install-list`).
