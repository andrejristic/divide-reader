#!/usr/bin/env bash
# Build DivideReader-Setup-<version>.exe (run in Git Bash on Windows)
#
# Contents: PyInstaller bundle of the app, bundled llama.cpp cpu + vulkan
# builds, icon; packed by Inno Setup into a per-user installer (no admin).
# The release build runs on GitHub's Windows runner (see .github/workflows/build-exe.yml).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
PY="${PYTHON:-$ROOT/.venv/Scripts/python.exe}"
VERSION="$("$PY" -c 'import divide_reader; print(divide_reader.__version__)')"
LLAMA_BUILD="b11429"
CACHE="$HERE/cache"
STAGE="$HERE/stage-win"
OUT="$ROOT/dist"
ISCC="${ISCC:-/c/Program Files (x86)/Inno Setup 6/ISCC.exe}"

declare -A LLAMA_SHA=(
  [win-cpu-x64]=1283323272b04cd07905816a597a0da810918102de958f4ff6f7bbaa70ed2efe
  [win-vulkan-x64]=1bfe78ad9168b79fa02bf67f6af9f5e17a966d824d77238517f7bef12ac73b36
)

fetch_llama() {  # $1 = flavour key, $2 = target dir
  local key="$1" dest="$2"
  local file="llama-${LLAMA_BUILD}-bin-${key}.zip"
  mkdir -p "$CACHE"
  if [ ! -f "$CACHE/$file" ]; then
    curl -fL --retry 3 -o "$CACHE/$file.part" \
      "https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_BUILD}/${file}"
    mv "$CACHE/$file.part" "$CACHE/$file"
  fi
  echo "${LLAMA_SHA[$key]}  $CACHE/$file" | sha256sum -c -
  local tmp
  tmp="$(mktemp -d)"
  "$PY" -m zipfile -e "$CACHE/$file" "$tmp"
  local src
  src="$(dirname "$(find "$tmp" -name llama-server.exe -type f | head -1)")"
  mkdir -p "$dest"
  cp "$src/llama-server.exe" "$dest/"
  cp "$src"/*.dll "$dest/" 2>/dev/null || true
  [ -f "$src/LICENSE" ] && cp "$src/LICENSE" "$dest/LICENSE.llama.cpp"
  rm -rf "$tmp"
}

echo "== PyInstaller bundle"
rm -rf "$ROOT/build/pyi" "$STAGE"
"$PY" -m PyInstaller --noconfirm --clean --onedir --windowed --name divide-reader \
  --icon "$HERE/divide-reader.ico" \
  --distpath "$ROOT/build/pyi/dist" --workpath "$ROOT/build/pyi/work" --specpath "$ROOT/build/pyi" \
  --collect-data divide_reader --collect-all trafilatura --collect-all justext --collect-data py3langid \
  --collect-submodules divide_reader --hidden-import divide_reader.gui.app \
  "$HERE/entry.py"

APP="$STAGE/divide-reader"
mkdir -p "$APP"
cp -a "$ROOT/build/pyi/dist/divide-reader/." "$APP/"

echo "== llama.cpp $LLAMA_BUILD"
fetch_llama win-cpu-x64 "$APP/llama/cpu"
fetch_llama win-vulkan-x64 "$APP/llama/vulkan"

cp "$HERE/divide-reader.ico" "$APP/"
cp "$ROOT/LICENSE" "$APP/LICENSE.txt"

echo "== Inno Setup"
mkdir -p "$OUT"
# MSYS2_ARG_CONV_EXCL: Git Bash would otherwise turn the /D options into paths.
MSYS2_ARG_CONV_EXCL="*" "$ISCC" "/DAppVersion=$VERSION" "/DSourceDir=$(cygpath -w "$APP")" "/DOutDir=$(cygpath -w "$OUT")" \
  "$(cygpath -w "$HERE/divide-reader.iss")"
echo "built $OUT/DivideReader-Setup-$VERSION.exe"
