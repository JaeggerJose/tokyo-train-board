# Demo recording for tokyo-train-board.
# Produces demo.gif with charmbracelet/vhs:  vhs demo.tape
# Install vhs:  brew install vhs   (https://github.com/charmbracelet/vhs)

Output demo.gif

Set Shell "bash"
Set FontSize 18
Set Width 1100
Set Height 640
Set Padding 18
Set Theme "Catppuccin Mocha"
Set TypingSpeed 60ms

# --- Yamanote: split-flap resolves into the board ---
Type "python3 main.py --once --line yamanote --station shinjuku"
Enter
Sleep 4s

# --- Ginza (orange) ---
Type "python3 main.py --once --line ginza --station ginza"
Enter
Sleep 4s

# --- Oedo (magenta) ---
Type "python3 main.py --once --line oedo --station tochomae"
Enter
Sleep 4s

# --- Statusline marquee (line-coloured, scrolls) ---
Type "for i in $(seq 1 6); do python3 main.py --mode statusline --line yamanote --station shinjuku --columns 72; echo; sleep 1; done"
Enter
Sleep 7s
