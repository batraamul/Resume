#!/bin/bash
# Build the Linux .tar.gz and .deb packages from the PyInstaller one-folder build.
#   packaging/linux/make_packages.sh 1.1.0
set -euo pipefail
VERSION="${1:?version}"
SRC="dist/ResumeIntelligenceStudio"
OUTDIR="dist/installer"
[ -d "$SRC" ] || { echo "Missing $SRC — run PyInstaller first." >&2; exit 1; }
mkdir -p "$OUTDIR"

# 1. Portable archive (extract anywhere; updates replace the folder in place).
cp packaging/linux/install-desktop-entry.sh "$SRC/"
chmod +x "$SRC/install-desktop-entry.sh" "$SRC/ResumeIntelligenceStudio"
tar -C dist -czf "$OUTDIR/ResumeIntelligenceStudio-${VERSION}-linux-x86_64.tar.gz" ResumeIntelligenceStudio

# 2. Debian/Ubuntu package (installs to /opt; needs administrator rights).
PKG="build/deb/resume-intelligence-studio"
rm -rf build/deb
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/256x256/apps" "$PKG/usr/share/icons/hicolor/512x512/apps"
cp -a "$SRC" "$PKG/opt/resume-intelligence-studio"
rm -f "$PKG/opt/resume-intelligence-studio/install-desktop-entry.sh"
ln -s /opt/resume-intelligence-studio/ResumeIntelligenceStudio "$PKG/usr/bin/resume-intelligence-studio"
cp packaging/linux/resume-intelligence-studio.desktop "$PKG/usr/share/applications/"
cp assets/icons/app-256.png "$PKG/usr/share/icons/hicolor/256x256/apps/resume-intelligence-studio.png"
cp assets/icons/app-512.png "$PKG/usr/share/icons/hicolor/512x512/apps/resume-intelligence-studio.png"
SIZE=$(du -sk "$PKG" | cut -f1)
cat > "$PKG/DEBIAN/control" <<CONTROL
Package: resume-intelligence-studio
Version: ${VERSION}
Section: office
Priority: optional
Architecture: amd64
Installed-Size: ${SIZE}
Depends: libegl1, libgl1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-keysyms1, libxcb-shape0, libfontconfig1, libdbus-1-3
Maintainer: Resume Intelligence Studio <resume-intelligence-studio@users.noreply.github.com>
Homepage: https://github.com/batraamul/Resume
Description: Verified master profile and tailored resumes
 Local-first desktop application for keeping one verified professional profile
 and producing ATS, government bio-data, academic and graphical resumes, with
 interview preparation and job-portal profile tools.
CONTROL
dpkg-deb --build --root-owner-group "$PKG" "$OUTDIR/resume-intelligence-studio_${VERSION}_amd64.deb"
echo "Built packages in $OUTDIR"
