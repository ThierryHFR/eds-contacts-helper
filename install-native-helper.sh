#!/bin/sh
set -eu

HELPER_NAME=eds_contacts_helper
INSTALL_DIR="$HOME/.local/bin"
MANIFEST_DIR="$HOME/.mozilla/native-messaging-hosts"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HELPER_PATH="$INSTALL_DIR/eds-contacts-helper.py"

mkdir -p "$INSTALL_DIR" "$MANIFEST_DIR"
cp "$SCRIPT_DIR/eds-contacts-helper.py" "$HELPER_PATH"
chmod +x "$HELPER_PATH"

cat > "$MANIFEST_DIR/$HELPER_NAME.json" <<EOF
{
  "name": "$HELPER_NAME",
  "description": "EDS Contacts helper for Thunderbird",
  "path": "$HELPER_PATH",
  "type": "stdio",
  "allowed_extensions": [
    "thierryhfr.eds-contacts-integration@addons.thunderbird.net",
    "eds-contacts-integration-v162@thierryh.local"
  ]
}
EOF

echo "Installed native messaging manifest: $MANIFEST_DIR/$HELPER_NAME.json"
echo "If listContacts fails with missing GI namespaces, run:"
echo "sudo apt install python3-gi gir1.2-edataserver-1.2 gir1.2-ebook-1.2 gir1.2-ebookcontacts-1.2"
