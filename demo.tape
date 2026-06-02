# Demo recording for tokyo-train-board.  Render with:  vhs demo.tape
# Install vhs:  brew install vhs   (https://github.com/charmbracelet/vhs)

Output demo.gif

Set Shell "bash"
Set FontSize 20
Set Width 1120
Set Height 760
Set Padding 18
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms

# --- Yamanote: split-flap resolves into a colour board (green) ---
Type "python3 main.py --once --line yamanote --station shinjuku"
Enter
Sleep 4s

# --- Ginza (orange) ---
Type "python3 main.py --once --line ginza --station ginza"
Enter
Sleep 3.5s

# --- Toei Oedo (magenta) ---
Type "python3 main.py --once --line oedo --station tochomae"
Enter
Sleep 3.5s

# --- Another city: JR Osaka Loop Line (red, loop) ---
Type "python3 main.py --once --line osaka-loop --station osaka"
Enter
Sleep 3.5s

# --- Kyoto: Randen tram to Arashiyama ---
Type "python3 main.py --once --line kyoto-randen --station arashiyama"
Enter
Sleep 3.5s

# --- Single-line statusline marquee (advances each second) ---
Type "for i in $(seq 7); do python3 main.py --mode statusline --line yamanote --station shinjuku --columns 56; echo; sleep 1; done"
Enter
Sleep 8s
