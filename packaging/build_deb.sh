#!/usr/bin/env bash
# Build divide-reader_<version>_amd64.deb
#
# Contents: /opt/divide-reader (PyInstaller bundle of the app, bundled llama.cpp
# cpu + vulkan builds, icon), /usr/bin/divide-reader, desktop entry, icon.
# The .deb runs on systems whose glibc is at least the build machine's, so the
# release build runs on Ubuntu 22.04 (see .github/workflows/build-deb.yml).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
VERSION="$("$PY" -c 'import divide_reader; print(divide_reader.__version__)')"
ARCH="${ARCH:-amd64}"
LLAMA_BUILD="b11429"
CACHE="$HERE/cache"
STAGE="$HERE/stage"
OUT="$ROOT/dist"

declare -A LLAMA_SHA=(
  [ubuntu-x64]=f6d25dde8f51133143d1453da4fd5f73b145127177612a283bf7995957af3392
  [ubuntu-vulkan-x64]=632c4e98feba2b94407a2130e3133e0c3aefb0ea1ab41337e926d8bfafdd0b74
)

fetch_llama() {  # $1 = flavour key, $2 = target dir
  local key="$1" dest="$2"
  local file="llama-${LLAMA_BUILD}-bin-${key}.tar.gz"
  mkdir -p "$CACHE"
  if [ ! -f "$CACHE/$file" ]; then
    curl -fL --retry 3 -o "$CACHE/$file.part" \
      "https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_BUILD}/${file}"
    mv "$CACHE/$file.part" "$CACHE/$file"
  fi
  echo "${LLAMA_SHA[$key]}  $CACHE/$file" | sha256sum -c -
  local tmp
  tmp="$(mktemp -d)"
  tar -xzf "$CACHE/$file" -C "$tmp"
  local src
  src="$(dirname "$(find "$tmp" -name llama-server -type f | head -1)")"
  mkdir -p "$dest"
  cp "$src/llama-server" "$dest/"
  cp "$src"/*.so* "$dest/" 2>/dev/null || true
  [ -f "$src/LICENSE" ] && cp "$src/LICENSE" "$dest/LICENSE.llama.cpp"
  rm -rf "$tmp"
}

echo "== PyInstaller bundle"
rm -rf "$ROOT/build/pyi" "$STAGE"
"$PY" -m PyInstaller --noconfirm --clean --onedir --name divide-reader \
  --distpath "$ROOT/build/pyi/dist" --workpath "$ROOT/build/pyi/work" --specpath "$ROOT/build/pyi" \
  --collect-data divide_reader --collect-all trafilatura --collect-all justext --collect-data py3langid \
  --collect-submodules divide_reader --hidden-import divide_reader.gui.app \
  "$HERE/entry.py"

APP="$STAGE/opt/divide-reader"
mkdir -p "$APP"
cp -a "$ROOT/build/pyi/dist/divide-reader/." "$APP/"

echo "== llama.cpp $LLAMA_BUILD"
if [ "$ARCH" = "amd64" ]; then
  fetch_llama ubuntu-x64 "$APP/llama/cpu"
  fetch_llama ubuntu-vulkan-x64 "$APP/llama/vulkan"
fi

cp "$HERE/divide-reader.svg" "$APP/"
cp "$ROOT/LICENSE" "$APP/LICENSE"

mkdir -p "$STAGE/usr/bin" "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/scalable/apps" \
         "$STAGE/usr/share/doc/divide-reader" "$STAGE/DEBIAN"
ln -s /opt/divide-reader/divide-reader "$STAGE/usr/bin/divide-reader"
cp "$HERE/divide-reader.desktop" "$STAGE/usr/share/applications/"
cp "$HERE/divide-reader.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/"
cat > "$STAGE/usr/share/doc/divide-reader/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: divide-reader

Files: *
Copyright: 2026 Andrej Ristić
License: GPL-3.0-or-later
 On Debian systems the full text is in /usr/share/common-licenses/GPL-3.

Files: opt/divide-reader/llama/*
Copyright: The ggml authors
License: MIT
 See opt/divide-reader/llama/*/LICENSE.llama.cpp
EOF

SIZE="$(du -sk "$STAGE" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: divide-reader
Version: $VERSION
Section: science
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE
Maintainer: Andrej Ristić <andrej.s.ristic@gmail.com>
Depends: libc6 (>= 2.34), libstdc++6, libgcc-s1, libgomp1, libssl3 | libssl3t64, libxcb-cursor0, libxkbcommon-x11-0, libegl1, libgl1, libfontconfig1, libdbus-1-3, xdg-utils
Recommends: libvulkan1, mesa-vulkan-drivers
Homepage: https://github.com/andrejristic/divide-reader
Description: count how many sides a text sorts its figures into
 Divide Reader reads websites, books and files sentence by sentence and
 counts, for each sentence, every way the speaker sorts its figures into
 sides (S). Five listeners read each unit; the report shows the most heard
 readings and measures comparable between sites and periods.
 .
 Includes llama.cpp for running a local model without internet, and
 connects to Ollama and online models (Gemini, Groq, Mistral, OpenRouter,
 Claude, OpenAI, Grok).
EOF

echo "== dpkg-deb"
mkdir -p "$OUT"
DEB="$OUT/divide-reader_${VERSION}_${ARCH}.deb"
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$DEB"
echo "built $DEB"
