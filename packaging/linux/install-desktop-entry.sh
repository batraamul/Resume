#!/bin/sh
# Add Resume Intelligence Studio to your applications menu (portable .tar.gz installs; no root needed).
DIR="$(cd "$(dirname "$0")" && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
mkdir -p "$APPS" "$ICONS"
cp "$DIR/_internal/assets/icons/app-256.png" "$ICONS/resume-intelligence-studio.png" 2>/dev/null || true
cat > "$APPS/resume-intelligence-studio.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=Resume Intelligence Studio
Comment=Verified master profile and tailored resumes
Exec="$DIR/ResumeIntelligenceStudio"
Icon=resume-intelligence-studio
Categories=Office;
Terminal=false
ENTRY
echo "Added Resume Intelligence Studio to your applications menu."
