#!/usr/bin/env bash
# Build a minimal static ffmpeg carrying exactly what these apps ask of it.
#
# BtbN's general-purpose GPL build is 140 MB and was 72% of the TUI bundle and
# 44% of the desktop one. Almost none of it is reachable from here: the apps
# mux video without re-encoding it, and transcode audio to one of six formats.
#
# What that needs, taken from yt-dlp's own ACODECS table rather than guessed:
#
#     app format   ext    encoder        extra
#     mp3          mp3    libmp3lame
#     aac          m4a    aac            -f adts
#     m4a          m4a    aac            -bsf:a aac_adtstoasc
#     opus         opus   libopus
#     flac         flac   flac
#     wav          wav    pcm_s16le      -f wav
#
# plus 'bv*+ba' merged into mp4 with -c copy. So: two external encoders
# (libmp3lame, libopus), the rest native, and demuxers for what YouTube serves.
#
# Usage: build-ffmpeg.sh <output-dir>
# Leaves a single static binary at <output-dir>/ffmpeg (ffmpeg.exe on Windows).
set -euo pipefail

OUT="${1:?usage: build-ffmpeg.sh <output-dir>}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

FFMPEG_VERSION="${FFMPEG_VERSION:-7.1.1}"
LAME_VERSION="${LAME_VERSION:-3.100}"
OPUS_VERSION="${OPUS_VERSION:-1.5.2}"

WORK="${WORK:-$(pwd)/.ffmpeg-build}"
PREFIX="$WORK/prefix"
mkdir -p "$WORK" "$PREFIX"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"

EXE=""
STATIC_LDFLAGS=""
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    EXE=".exe"
    # Without this the exe wants the MSYS2 runtime DLLs, which are not shipped.
    STATIC_LDFLAGS="-static"
    ;;
esac

fetch() {  # url sha256 filename
  local url="$1" sum="$2" file="$WORK/$3"
  if [ ! -f "$file" ]; then
    curl -fsSL "$url" -o "$file.part"
    mv "$file.part" "$file"
  fi
  echo "$sum  $file" | shasum -a 256 -c - >/dev/null 2>&1 \
    || echo "$sum  $file" | sha256sum -c - >/dev/null
}

cd "$WORK"

# ── libmp3lame — the only mp3 encoder ffmpeg can use ─────────────────────────
if [ ! -f "$PREFIX/lib/libmp3lame.a" ]; then
  fetch "https://downloads.sourceforge.net/project/lame/lame/${LAME_VERSION}/lame-${LAME_VERSION}.tar.gz" \
        "ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e" \
        "lame-${LAME_VERSION}.tar.gz"
  rm -rf "lame-${LAME_VERSION}"
  tar xzf "lame-${LAME_VERSION}.tar.gz"
  cd "lame-${LAME_VERSION}"
  # frontend is the `lame` CLI; we only want the library
  ./configure --prefix="$PREFIX" --enable-static --disable-shared \
              --disable-frontend --disable-decoder >/dev/null
  make -j"$JOBS" >/dev/null && make install >/dev/null
  cd "$WORK"
fi

# ── libopus — ffmpeg's native opus encoder is not usable for this ────────────
if [ ! -f "$PREFIX/lib/libopus.a" ]; then
  fetch "https://downloads.xiph.org/releases/opus/opus-${OPUS_VERSION}.tar.gz" \
        "65c1d2f78b9f2fb20082c38cbe47c951ad5839345876e46941612ee87f9a7ce1" \
        "opus-${OPUS_VERSION}.tar.gz"
  rm -rf "opus-${OPUS_VERSION}"
  tar xzf "opus-${OPUS_VERSION}.tar.gz"
  cd "opus-${OPUS_VERSION}"
  ./configure --prefix="$PREFIX" --enable-static --disable-shared \
              --disable-doc --disable-extra-programs >/dev/null
  make -j"$JOBS" >/dev/null && make install >/dev/null
  cd "$WORK"
fi

# ── ffmpeg ───────────────────────────────────────────────────────────────────
fetch "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" \
      "733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1" \
      "ffmpeg-${FFMPEG_VERSION}.tar.xz"
rm -rf "ffmpeg-${FFMPEG_VERSION}"
tar xf "ffmpeg-${FFMPEG_VERSION}.tar.xz"
cd "ffmpeg-${FFMPEG_VERSION}"

# --disable-everything, then name what is reachable from these two apps. Adding
# a format to the apps means adding its encoder and muxer here;
# tests/test_ffmpeg_build.py fails if the two lists drift apart.
./configure \
  --prefix="$PREFIX" \
  --extra-cflags="-I$PREFIX/include" \
  --extra-ldflags="-L$PREFIX/lib $STATIC_LDFLAGS" \
  --pkg-config-flags="--static" \
  --disable-everything \
  --disable-doc --disable-htmlpages --disable-manpages --disable-podpages --disable-txtpages \
  --disable-ffplay --disable-network --disable-autodetect \
  --disable-debug --enable-small \
  --enable-gpl --enable-libmp3lame --enable-libopus \
  --enable-protocol=file,pipe \
  --enable-demuxer=mov,matroska,ogg,mp3,flac,wav,aac,m4v,mpegts \
  --enable-muxer=mp4,ipod,mp3,adts,ogg,opus,flac,wav,matroska \
  --enable-decoder=aac,aac_latm,mp3,mp3float,opus,vorbis,flac,alac,ac3,pcm_s16le,pcm_s16be,pcm_f32le \
  --enable-encoder=aac,libmp3lame,libopus,flac,pcm_s16le \
  --enable-parser=aac,aac_latm,mpegaudio,flac,opus,vorbis,h264,hevc,vp9,av1 \
  --enable-bsf=aac_adtstoasc,extract_extradata,h264_mp4toannexb,hevc_mp4toannexb,vp9_superframe \
  --enable-filter=aresample,anull,aformat,null,copy,atrim,trim,concat \
  ${FFMPEG_EXTRA_CONFIGURE:-} \
  >/dev/null

make -j"$JOBS" >/dev/null
cp "ffmpeg${EXE}" "$OUT/ffmpeg${EXE}"
strip "$OUT/ffmpeg${EXE}" 2>/dev/null || true

printf 'built %s -> %s (%s)\n' "ffmpeg ${FFMPEG_VERSION}" "$OUT/ffmpeg${EXE}" \
       "$(du -h "$OUT/ffmpeg${EXE}" | cut -f1)"
