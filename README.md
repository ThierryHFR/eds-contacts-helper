# eds-contacts-helper

Local Native Messaging helper for the Thunderbird extension [`eds-contacts-integration`](https://github.com/ThierryHFR/eds-contacts-integration).

## Purpose

The helper lets the extension access Evolution Data Server (EDS) without loading GNOME or libebook components inside Thunderbird.

```text
Thunderbird Extension
        ⇅ Native Messaging (local JSON messages)
eds-contacts-helper
        ⇅ libebook / EDS / D-Bus
Evolution Data Server
```

Version 2.0.1 supports:

* listing EDS address books and contacts;
* detecting EDS contact changes;
* adding a contact to EDS;
* diagnostics for the required GObject Introspection namespaces.

The companion extension uses these operations for EDS → Thunderbird synchronization and, optionally, for adding newly created Thunderbird contacts to EDS. Updating or deleting an EDS contact from Thunderbird is not currently implemented.

## Requirements

* Linux (tested on Linux Mint 22.x and Ubuntu 24.x)
* Thunderbird 140 ESR or newer
* Python 3
* Evolution Data Server and its GObject Introspection bindings

On Debian, Ubuntu or Linux Mint:

```bash
sudo apt install \
  python3 \
  python3-gi \
  gir1.2-edataserver-1.2 \
  gir1.2-ebook-1.2 \
  gir1.2-ebookcontacts-1.2
```

## Installation

Extract a release archive and run:

```bash
./install-native-helper.sh
```

The installer copies:

* the executable to `~/.local/bin/eds-contacts-helper.py`;
* the Native Messaging manifest to `~/.mozilla/native-messaging-hosts/eds_contacts_helper.json`.

The manifest only authorizes the production extension identifier:

```text
thierryhfr.eds-contacts-integration@addons.thunderbird.net
```

Restart Thunderbird after installing or updating the helper.

## Diagnostics

```bash
~/.local/bin/eds-contacts-helper.py --test diagnostics
~/.local/bin/eds-contacts-helper.py --test listSources
~/.local/bin/eds-contacts-helper.py --test listContacts
```

Technical logs are stored in `~/.cache/eds-contacts-helper.log`.

## Privacy and security

The helper communicates locally through standard input and output. It does not make network requests or send telemetry. It only accepts Native Messaging connections from the explicitly authorized Thunderbird extension ID. Contact data is processed in memory and is not intentionally written to the diagnostic log.

Synchronization is disabled by default in the companion extension and requires explicit user consent.

## License

GPL-3.0-only
