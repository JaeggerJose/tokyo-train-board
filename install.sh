#!/usr/bin/env bash
# jrboard one-command installer — works on ANY box with python3 (>=3.11).
#
# Why this exists: tokyo-train-board has ZERO runtime dependencies, so it does
# not actually need pip. On a locked-down Debian/Ubuntu (PEP 668, no pip, no
# venv, no pipx) every documented `pip install` path fails. This script tries
# the nice paths first, then falls back to a git-clone + launcher that always
# works, and finally wires the Claude Code statusLine for you.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/JaeggerJose/tokyo-train-board/main/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- --columns 90 --line oedo --city Tokyo --csl
#
# Pass-through flags (all optional, forwarded to `--install-statusline`):
#   --columns N --line KEY --station KEY --city NAME --minitable
# Installer flags:
#   --csl              also install the csl theme into ~/.config/csl/themes
#   --offline          force the git-clone path (skip pip/pipx) — hackable checkout
#   --no-statusline    install the tool only; don't touch settings.json
#   --help             show this help and exit
#
# Env overrides (advanced / testing):
#   JRBOARD_REPO  git URL           (default: the GitHub repo)
#   JRBOARD_REF   branch/tag        (default: main)
#   JR_PREFIX     clone-fallback dir(default: ~/.local/share/jrboard)
#   JR_BIN        launcher dir      (default: ~/.local/bin)
#   JR_DRYRUN=1   print actions, mutate nothing (used by the test suite)

set -euo pipefail

JRBOARD_REPO="${JRBOARD_REPO:-https://github.com/JaeggerJose/tokyo-train-board}"
JRBOARD_REF="${JRBOARD_REF:-main}"
JR_PREFIX="${JR_PREFIX:-$HOME/.local/share/jrboard}"
JR_BIN="${JR_BIN:-$HOME/.local/bin}"
JR_DRYRUN="${JR_DRYRUN:-0}"

WANT_CSL=0
WANT_STATUSLINE=1
FORCE_CLONE=0
PASS_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --csl)            WANT_CSL=1 ;;
    --offline)        FORCE_CLONE=1 ;;
    --no-statusline)  WANT_STATUSLINE=0 ;;
    --minitable)      PASS_ARGS+=("--mode" "minitable") ;;
    --columns|--line|--station|--city)
                      PASS_ARGS+=("$1" "${2:?$1 needs a value}"); shift ;;
    --help|-h)        sed -n '2,33p' "$0"; exit 0 ;;
    *)                echo "jrboard-install: unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

c_grn=$'\033[32m'; c_yel=$'\033[33m'; c_red=$'\033[31m'; c_dim=$'\033[2m'; c_rst=$'\033[0m'
say()  { printf '%s\n' "${c_dim}jrboard-install:${c_rst} $*"; }
ok()   { printf '%s\n' "${c_grn}✓${c_rst} $*"; }
warn() { printf '%s\n' "${c_yel}!${c_rst} $*" >&2; }
die()  { printf '%s\n' "${c_red}✗ jrboard-install: $*${c_rst}" >&2; exit 1; }
# RUN echoes in dry-run, executes otherwise — keeps the script fully testable.
RUN()  { if [ "$JR_DRYRUN" = "1" ]; then printf 'DRYRUN: %s\n' "$*"; else "$@"; fi; }

# --- 1. require python3 >= 3.11 (the ONE real system dependency) ------------- #
PY="$(command -v python3 || true)"
[ -n "$PY" ] || die "python3 not found. Install it first (Debian/Ubuntu: sudo apt install python3)."
if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,11) else 1)'; then
  die "python3 >= 3.11 required; found $("$PY" -V 2>&1). Upgrade python3."
fi
ok "python3 found: $PY ($("$PY" -V 2>&1))"

# --- 2. get a runnable jrboard: pip --user -> pipx -> git-clone fallback ----- #
# RUNNER is how the installed board is invoked afterwards (python+module, or a
# main.py path for the clone fallback). install-statusline reuses it verbatim.
RUNNER_PY="$PY"
RUNNER_SCRIPT=""   # empty => use `-m jrboard`; set => `python <script>`
INSTALL_METHOD=""

try_pip() {
  "$PY" -m pip --version >/dev/null 2>&1 || return 1
  say "trying: pip install --user tokyo-train-board"
  RUN "$PY" -m pip install --user -q tokyo-train-board 2>/dev/null || return 1
  "$PY" -c 'import jrboard' >/dev/null 2>&1 || [ "$JR_DRYRUN" = "1" ] || return 1
  INSTALL_METHOD="pip --user"; return 0
}
try_pipx() {
  command -v pipx >/dev/null 2>&1 || return 1
  say "trying: pipx install tokyo-train-board"
  RUN pipx install tokyo-train-board >/dev/null 2>&1 || return 1
  INSTALL_METHOD="pipx"; RUNNER_PY="python3"; return 0
}
fallback_clone() {
  say "falling back to git clone (zero-dependency, no pip/venv/sudo needed)"
  command -v git >/dev/null 2>&1 || die "git not found and pip/pipx unavailable. Install git or pip."
  if [ -d "$JR_PREFIX/.git" ]; then
    RUN git -C "$JR_PREFIX" pull --ff-only -q || warn "could not update existing clone; using it as-is"
  else
    RUN rm -rf "$JR_PREFIX"
    RUN git clone --depth 1 --branch "$JRBOARD_REF" -q "$JRBOARD_REPO" "$JR_PREFIX" \
      || die "git clone failed from $JRBOARD_REPO"
  fi
  # Launcher on PATH so `jrboard` works in the shell too.
  RUN mkdir -p "$JR_BIN"
  if [ "$JR_DRYRUN" = "1" ]; then
    printf 'DRYRUN: write launcher %s -> %s/main.py\n' "$JR_BIN/jrboard" "$JR_PREFIX"
  else
    cat > "$JR_BIN/jrboard" <<LAUNCH
#!/usr/bin/env bash
exec "$PY" "$JR_PREFIX/main.py" "\$@"
LAUNCH
    chmod +x "$JR_BIN/jrboard"
  fi
  INSTALL_METHOD="git clone"; RUNNER_SCRIPT="$JR_PREFIX/main.py"
}

if [ "$FORCE_CLONE" = "1" ]; then
  fallback_clone
else
  try_pip || try_pipx || fallback_clone
fi
ok "installed via: $INSTALL_METHOD"

# How we invoke the board from here on (clone => main.py path; else -m jrboard).
board() {
  if [ -n "$RUNNER_SCRIPT" ]; then RUN "$RUNNER_PY" "$RUNNER_SCRIPT" "$@";
  else RUN "$RUNNER_PY" -m jrboard "$@"; fi
}

# --- 3. wire the Claude Code statusLine (unless opted out) ------------------- #
if [ "$WANT_STATUSLINE" = "1" ]; then
  say "wiring Claude Code statusLine (~/.claude/settings.json, auto-backed-up)"
  board --install-statusline "${PASS_ARGS[@]+"${PASS_ARGS[@]}"}" \
    || warn "install-statusline did not complete (is Claude Code present?)"
else
  say "skipping statusLine wiring (--no-statusline)"
fi

# --- 4. optional: drop the csl theme ----------------------------------------- #
if [ "$WANT_CSL" = "1" ]; then
  say "installing csl theme into ~/.config/csl/themes"
  board --install-csl-theme || warn "could not install csl theme"
  echo "  then activate it with:  csl set jr-board"
fi

# --- 5. PATH advisory -------------------------------------------------------- #
case ":$PATH:" in
  *":$JR_BIN:"*) : ;;
  *) warn "$JR_BIN is not on your PATH. Add this to your shell rc:"
     printf '       %s\n' "export PATH=\"$JR_BIN:\$PATH\"" ;;
esac

ok "done. statusLine updates within ~1s, or on the next Claude Code session."
