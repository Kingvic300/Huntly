#!/bin/sh
# Install Huntly on Linux with one command:
#
#   curl -fsSL https://kingvic300.github.io/Huntly/install.sh | sudo sh
#
# Debian, Ubuntu, Kali (apt) and Fedora, RHEL, openSUSE (dnf, yum, zypper): adds Huntly's signed
# package repository once, then installs Huntly. After that your package manager installs and
# updates it like any other package (sudo apt upgrade, sudo dnf upgrade, sudo zypper update).
# Any other distribution: installs the AppImage to /opt/huntly, which updates itself.
set -eu

BASE="https://kingvic300.github.io/Huntly"
KEYRING="/usr/share/keyrings/huntly.gpg"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo: curl -fsSL $BASE/install.sh | sudo sh" >&2
  exit 1
fi
case "$(uname -m)" in
  x86_64|amd64) ;;
  *) echo "Huntly's Linux builds are for 64-bit Intel/AMD (x86_64) only." >&2; exit 1 ;;
esac

if command -v apt-get >/dev/null 2>&1; then
  echo "Adding Huntly's APT repository..."
  install -d -m 0755 /usr/share/keyrings
  curl -fsSL "$BASE/huntly.gpg" -o "$KEYRING.tmp" && mv "$KEYRING.tmp" "$KEYRING" && chmod 0644 "$KEYRING"
  echo "deb [arch=amd64 signed-by=$KEYRING] $BASE/apt stable main" > /etc/apt/sources.list.d/huntly.list
  apt-get update
  apt-get install -y huntly
  echo "Done. Updates arrive with: sudo apt upgrade"
elif command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then
  echo "Adding Huntly's RPM repository..."
  curl -fsSL "$BASE/huntly.repo" -o /etc/yum.repos.d/huntly.repo
  if command -v dnf >/dev/null 2>&1; then dnf install -y huntly; else yum install -y huntly; fi
  echo "Done. Updates arrive with: sudo dnf upgrade"
elif command -v zypper >/dev/null 2>&1; then
  echo "Adding Huntly's RPM repository..."
  zypper --non-interactive --gpg-auto-import-keys addrepo --refresh "$BASE/huntly.repo"
  zypper --non-interactive --gpg-auto-import-keys install huntly
  echo "Done. Updates arrive with: sudo zypper update"
else
  echo "No apt, dnf, yum or zypper found; installing the AppImage..."
  url="$(curl -fsSL https://api.github.com/repos/Kingvic300/Huntly/releases/latest | grep -o 'https://[^"]*_amd64\.AppImage' | head -n 1)"
  [ -n "$url" ] || { echo "Could not find the latest AppImage." >&2; exit 1; }
  install -d -m 0755 /opt/huntly
  curl -fL "$url" -o /opt/huntly/Huntly.AppImage
  chmod 0755 /opt/huntly/Huntly.AppImage
  chown -R "${SUDO_USER:-root}" /opt/huntly  # lets the AppImage update itself without sudo
  ln -sf /opt/huntly/Huntly.AppImage /usr/local/bin/huntly
  cat > /usr/share/applications/huntly.desktop <<EOF
[Desktop Entry]
Name=Huntly
Comment=Private, local job-hunting assistant
Exec=/opt/huntly/Huntly.AppImage
Terminal=false
Type=Application
Categories=Office;
EOF
  echo "Done. Run 'huntly' or open Huntly from your applications menu. It updates itself."
fi
