#!/usr/bin/env python3
import os
import sys
import time
import unicodedata
import re
from datetime import datetime

# --- Colors ---
GREEN_FG = "\033[32m"
GREEN_BG = "\033[42m\033[37m"
ORANGE = "\033[33m"
RESET = "\033[0m"
BOLD = "\033[1m"
BLACK_BG = "\033[40m\033[37m"

def get_visual_width(text):
    """Calculate terminal display width considering CJK and ANSI codes."""
    plain = re.sub(r'\033\[[0-9;]*m', '', text)
    width = 0
    for char in plain:
        if unicodedata.east_asian_width(char) in ('W', 'F'):
            width += 2
        else:
            width += 1
    return width

def safe_pad(text, target_w, align='left'):
    """Strictly ensures the output visual width equals target_w."""
    w = get_visual_width(text)
    pad_total = target_w - w
    if pad_total <= 0: return text
    
    if align == 'left':
        return text + (" " * pad_total)
    elif align == 'right':
        return (" " * pad_total) + text
    else: # center
        l = pad_total // 2
        r = pad_total - l
        return (" " * l) + text + (" " * r)

def draw_station_sign(W):
    IW = W - 2 # Internal width: 58
    print("+" + "-" * IW + "+")
    
    # Each row is passed through safe_pad to ensure it hits exactly IW characters.
    
    # Line 1: [SJK] and [山][區]
    sjk_part = f"  {BLACK_BG} SJK {RESET}"
    line1 = sjk_part + " " * 36 + "[山][區] "
    print("|" + safe_pad(line1, IW) + "|")
    
    # Line 2: [JY 17] and Centered Station Name
    jy17_part = f"  {GREEN_BG} JY 17 {RESET}"
    name_part = safe_pad(f"{BOLD}新  宿{RESET}", 42, 'center')
    line2 = jy17_part + name_part + "     "
    print("|" + safe_pad(line2, IW) + "|")
    
    # Line 3: Sub names (Japanese, English) - Centered
    sub_names = "しんじゅく  Shinjuku"
    print("|" + safe_pad(sub_names, IW, 'center') + "|")
    
    # Line 4: Green Navigation Bar
    prev_jp, curr_jp, next_jp = "代々木", "■", "新大久保 ▶"
    bar_content = ( "  " + safe_pad(prev_jp, 16, 'left') + 
                    safe_pad(curr_jp, 22, 'center') + 
                    safe_pad(next_jp, 16, 'right') + "  " )
    print("|" + GREEN_BG + safe_pad(bar_content, IW) + RESET + "|")
    
    # Line 5: English
    prev_en, curr_en, next_en = "Yoyogi", "Shinjuku", "Shin-Okubo"
    line5 = ( "  " + safe_pad(prev_en, 16, 'left') + 
              safe_pad(curr_en, 22, 'center') + 
              safe_pad(next_en, 16, 'right') + "  " )
    print("|" + safe_pad(line5, IW) + "|")
    print("+" + "-" * IW + "+")

def draw_timetable(W):
    IW = W - 2
    now = datetime.now()
    trains = []
    for i in range(1, 4):
        t1 = (now.minute + i * 4) % 60
        h1 = now.hour + ((now.minute + i * 4) // 60)
        trains.append({"t": f"{h1:02d}:{t1:02d}", "d": "渋谷・品川方面", "p": "各駅停車", "tr": "14"})
        t2 = (now.minute + i * 4 + 2) % 60
        h2 = now.hour + ((now.minute + i * 4 + 2) // 60)
        trains.append({"t": f"{h2:02d}:{t2:02d}", "d": "池袋・上野方面", "p": "各駅停車", "tr": "15"})
    trains = sorted(trains, key=lambda x: x['t'])[:6]

    # Header
    h = f" {safe_pad('時刻', 6)} | {safe_pad('種別', 10)} | {safe_pad('行先 (方面)', 26)} | {safe_pad('番線', 4)} "
    print("|" + safe_pad(h, IW) + "|")
    print("|" + "-" * IW + "|")
    
    for t in trains:
        t_str = f"{ORANGE}{t['t']}{RESET}"
        p_str = f"{GREEN_FG}{t['p']}{RESET}"
        row = (f" {safe_pad(t_str, 6)} | "
               f"{safe_pad(p_str, 10)} | "
               f"{safe_pad(t['d'], 26)} | "
               f"{safe_pad(t['tr'], 4)} ")
        print("|" + safe_pad(row, IW) + "|")
    print("+" + "-" * IW + "+")

def main():
    while True:
        print("\033[H\033[J", end="")
        draw_station_sign(60)
        draw_timetable(60)
        time.sleep(10)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程式已終止")
        sys.exit(0)
