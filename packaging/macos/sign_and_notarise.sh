#!/bin/bash
# Optional: sign the .app with a Developer ID certificate and notarise it. Runs only when the
# MACOS_CERTIFICATE_P12 secret is configured (see docs/RELEASING.md); otherwise the app stays ad-hoc signed.
set -euo pipefail
APP="dist/Resume Intelligence Studio.app"
KEYCHAIN="$RUNNER_TEMP/build.keychain-db"
KEYCHAIN_PASSWORD="$(openssl rand -hex 16)"
echo "$MACOS_CERTIFICATE_P12" | base64 --decode > "$RUNNER_TEMP/cert.p12"
security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
security set-keychain-settings -lut 21600 "$KEYCHAIN"
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
security import "$RUNNER_TEMP/cert.p12" -P "$MACOS_CERTIFICATE_PASSWORD" -A -t cert -f pkcs12 -k "$KEYCHAIN"
security list-keychains -d user -s "$KEYCHAIN"
security set-key-partition-list -S apple-tool:,apple: -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
codesign --deep --force --options runtime --timestamp --sign "$MACOS_SIGN_IDENTITY" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
ditto -c -k --keepParent "$APP" "$RUNNER_TEMP/notarise.zip"
xcrun notarytool submit "$RUNNER_TEMP/notarise.zip" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
  --password "$APPLE_APP_PASSWORD" --wait
xcrun stapler staple "$APP"
rm -f "$RUNNER_TEMP/cert.p12"
