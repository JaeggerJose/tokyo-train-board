#!/usr/bin/env python3
"""Apply official line colours (24-bit truecolor) to every jrboard data file.

Official hex values are sourced from each line's JA Wikipedia 路線色 infobox
(operator-canonical). We emit truecolor ANSI so the rendered colour matches the
hex exactly instead of the nearest xterm-256 approximation. The badge background
gets a luminance-chosen contrasting foreground (dark text on light colours,
white text on dark colours) so the line code stays readable.

Run:  python3 scripts/apply_colors.py
"""

from __future__ import annotations

import json
import pathlib

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "jrboard" / "data"

# key -> (official hex, human-readable colour name). Source: JA Wikipedia 路線色.
OFFICIAL: dict[str, tuple[str, str]] = {
    "yamanote":       ("#9ACD32", "黄緑6号 / yellow-green"),
    "chuo":           ("#F15A22", "朱色1号 / vermilion-orange"),
    "sobu":           ("#FFD400", "黄色5号 / canary yellow"),
    "keihintohoku":   ("#00B2E5", "青22号 / sky blue"),
    "saikyo":         ("#00AC9A", "緑15号 / green"),
    "shonanshinjuku": ("#E31F26", "JR東 路線図 赤 / red"),
    "yokosuka":       ("#0067C0", "スカ色系 / navy blue"),
    "ginza":          ("#FF9500", "オレンジ / orange"),
    "marunouchi":     ("#F62E36", "赤 / red"),
    "hibiya":         ("#B5B5AC", "シルバー / silver-grey"),
    "tozai":          ("#009BBF", "スカイ / sky blue"),
    "chiyoda":        ("#00BB85", "グリーン / green"),
    "yurakucho":      ("#C1A470", "ゴールド / gold"),
    "hanzomon":       ("#8F76D6", "パープル / purple"),
    "namboku":        ("#00AC9B", "エメラルド / emerald"),
    "fukutoshin":     ("#9C5E31", "ブラウン / brown"),
    "asakusa":        ("#EC6E65", "ローズ / rose-red"),
    "mita":           ("#0079C2", "ブルー / blue"),
    "shinjuku":       ("#B0BF1E", "リーフ / leaf-green"),
    "oedo":           ("#B6007A", "マゼンタ / magenta"),
}

# Contrasting foregrounds for the badge background block.
DARK_TEXT = (26, 26, 26)      # near-black
LIGHT_TEXT = (255, 255, 255)  # white
# Perceived-brightness threshold (ITU-R BT.601 weights, 0-255). Above => dark text.
BRIGHTNESS_THRESHOLD = 140


def hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    h = hex_code.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def brightness(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return (r * 299 + g * 587 + b * 114) / 1000


def fg_escape(rgb: tuple[int, int, int]) -> str:
    return f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def bg_escape(rgb: tuple[int, int, int]) -> str:
    return f"\033[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def build_color(hex_code: str, name: str) -> dict:
    rgb = hex_to_rgb(hex_code)
    text = DARK_TEXT if brightness(rgb) > BRIGHTNESS_THRESHOLD else LIGHT_TEXT
    return {
        "name": name,
        "hex": hex_code.upper(),
        "ansi_fg": fg_escape(rgb),                       # line colour as text
        "ansi_bg": bg_escape(rgb) + fg_escape(text),     # badge block: bg + readable text
    }


def main() -> int:
    changed = 0
    for key, (hex_code, name) in OFFICIAL.items():
        path = DATA_DIR / f"{key}.json"
        if not path.exists():
            print(f"  ! missing {path}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        data["color"] = build_color(hex_code, name)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        text = "dark" if brightness(hex_to_rgb(hex_code)) > BRIGHTNESS_THRESHOLD else "white"
        print(f"  ✓ {key:15} {hex_code}  badge-text={text}")
        changed += 1
    print(f"\nupdated {changed}/{len(OFFICIAL)} line files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
