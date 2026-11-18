#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Build a pinned ARM soft-float libc outside the repository. No device writes.
set -eu
root=${YAMAHA_MUSL_BUILD_DIR:?Set absolute musl build directory outside Git}
case "$root" in /*) ;; *)
    echo 'Use an absolute build directory' >&2
    exit 1
    ;;
esac
version=1.2.5
gcc_major=$(arm-linux-gnueabi-gcc -dumpversion | cut -d. -f1)
gcc_notice=/usr/share/doc/gcc-$gcc_major-base/copyright
[ -f "$gcc_notice" ] || {
    echo "Missing $gcc_notice" >&2
    exit 1
}
digest=a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4
mkdir -p "$root"
cd "$root"
archive=musl-$version.tar.gz
if [ ! -f "$archive" ]; then
    curl --fail --location --max-time 120 "https://musl.libc.org/releases/$archive" -o "$archive.download"
    mv "$archive.download" "$archive"
fi
echo "$digest  $archive" | sha256sum -c -
# Re-extract the verified archive; a previous local edit must not enter the build.
tar -xzf "$archive"
cd "musl-$version"
[ ! -f config.mak ] || make clean
CC=arm-linux-gnueabi-gcc AR=arm-linux-gnueabi-ar RANLIB=arm-linux-gnueabi-ranlib \
    ./configure --target=arm-linux-musleabi --prefix="$root/musl-arm" --disable-shared
make -j"${YAMAHA_BUILD_JOBS:-4}"
make install
# Only kernel UAPI headers, never glibc headers, are added to the musl include tree.
for part in linux asm asm-generic; do
    cp -R "/usr/arm-linux-gnueabi/include/$part" "$root/musl-arm/include/"
done
mkdir -p "$root/musl-arm/third-party"
cp COPYRIGHT "$root/musl-arm/third-party/musl-COPYRIGHT.txt"
cp "$root/$archive" "$root/musl-arm/third-party/"
cp "$gcc_notice" "$root/musl-arm/third-party/GCC-copyright.txt"
cp /usr/share/common-licenses/GPL-3 "$root/musl-arm/third-party/GPL-3.txt"
printf '%s\n' "musl-$version $digest" >"$root/musl-arm/third-party/build-provenance.txt"
arm-linux-gnueabi-gcc --version >>"$root/musl-arm/third-party/build-provenance.txt"
echo "Ready: YAMAHA_MUSL_PREFIX=$root/musl-arm"
