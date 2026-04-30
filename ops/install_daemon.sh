#!/usr/bin/env bash
# Install + load the crawler daemon under launchd.
#
# Idempotent: re-running rewrites the plist and reloads launchd.
#
# Usage:
#   ops/install_daemon.sh                    # use defaults below
#   CORPUS_ROOT=/data/corpus ops/install_daemon.sh   # override

set -euo pipefail

# ---- Defaults --------------------------------------------------------------
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
CORPUS_ROOT="${CORPUS_ROOT:-/Volumes/T9/gemma-god/corpus_v2}"
STATE_DIR="${STATE_DIR:-/Volumes/T9/gemma-god/daemon-state}"
LABEL="np.gemma-god.crawler"
PLIST_TEMPLATE="$REPO_ROOT/ops/${LABEL}.plist.template"
PLIST_DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"

# Resolve `claude` to an absolute path. nvm-installed claude lives outside
# launchd's default PATH; substituting the absolute path means the daemon
# doesn't depend on PATH at runtime.
if ! CLAUDE_BIN="$(command -v claude 2>/dev/null)"; then
    echo "error: 'claude' not found on PATH. Activate nvm and install" >&2
    echo "claude-code first:" >&2
    echo "  nvm use --lts && npm install -g @anthropic-ai/claude-code" >&2
    exit 2
fi

# Same for pdftotext (Poppler) — used as the secondary PDF parser when the
# pure-Rust pdf_extract panics or returns thin text. Conda-forge installs
# under $HOME/miniconda3/bin which isn't on the launchd PATH.
if ! PDFTOTEXT_BIN="$(command -v pdftotext 2>/dev/null)"; then
    echo "error: 'pdftotext' not found on PATH. Install Poppler:" >&2
    echo "  macOS: brew install poppler   (or: conda install -c conda-forge poppler)" >&2
    echo "  Linux: apt install poppler-utils  /  dnf install poppler-utils" >&2
    exit 2
fi

# ---- Pre-flight checks -----------------------------------------------------
[ -f "$PLIST_TEMPLATE" ] || { echo "error: missing template $PLIST_TEMPLATE" >&2; exit 2; }
[ -d "$REPO_ROOT/.git" ] || { echo "error: $REPO_ROOT is not a git repo (auto-commit needs git)" >&2; exit 2; }

# Build the release binary if it isn't already built or is older than src/.
if [ ! -x "$REPO_ROOT/target/release/crawl" ] \
   || [ "$REPO_ROOT/src" -nt "$REPO_ROOT/target/release/crawl" ]; then
    echo "[install] building release binary..."
    (cd "$REPO_ROOT" && cargo build --release --bin crawl)
fi

mkdir -p "$STATE_DIR"
mkdir -p "$(dirname "$PLIST_DEST")"

# ---- Substitute template + write plist -------------------------------------
echo "[install] writing $PLIST_DEST"
sed \
    -e "s|@REPO_ROOT@|$REPO_ROOT|g" \
    -e "s|@CORPUS_ROOT@|$CORPUS_ROOT|g" \
    -e "s|@STATE_DIR@|$STATE_DIR|g" \
    -e "s|@CLAUDE_BIN@|$CLAUDE_BIN|g" \
    -e "s|@PDFTOTEXT_BIN@|$PDFTOTEXT_BIN|g" \
    "$PLIST_TEMPLATE" > "$PLIST_DEST"

# Validate the plist parses before asking launchd to load it. plutil exits
# non-zero on malformed plist and prints the offending position.
plutil -lint "$PLIST_DEST"

# ---- Reload launchd --------------------------------------------------------
# `bootout` is the modern replacement for `unload`; ignore failure if the
# service isn't currently loaded (first install).
echo "[install] reloading launchd"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo
echo "[install] done."
echo "  state:    $STATE_DIR"
echo "  pid file: $STATE_DIR/daemon.pid"
echo "  stdout:   $STATE_DIR/daemon.stdout.log"
echo "  stderr:   $STATE_DIR/daemon.stderr.log"
echo
echo "  status:   launchctl print gui/$(id -u)/$LABEL | head -40"
echo "  tail log: tail -f $STATE_DIR/daemon.stderr.log"
echo "  stop:     ops/uninstall_daemon.sh"
