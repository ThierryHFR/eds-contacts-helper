# eds-contacts-helper

Native Messaging helper for Thunderbird ↔ Evolution Data Server (EDS) contact synchronization.

## Overview

`eds-contacts-helper` is a Linux Native Messaging bridge used by the Thunderbird extension `eds-contacts-integration`.

It allows Thunderbird to synchronize contacts with Evolution Data Server (EDS) without loading GNOME / libebook components directly inside Thunderbird.

This architecture avoids instability and crashes caused by direct EDS access from Thunderbird WebExtensions.

---

# Features

* Bidirectional synchronization

  * EDS → Thunderbird
  * Thunderbird → EDS
* Event-driven synchronization
* Native Messaging integration
* Evolution Data Server support
* Thunderbird 140 ESR compatible
* External helper process isolation
* Linux desktop integration

---

# Architecture

```text
Thunderbird Extension
        ⇅ Native Messaging
eds-contacts-helper
        ⇅ libebook / EDS / DBus
Evolution Data Server
```

The helper runs outside Thunderbird and communicates through JSON messages.

---

# Requirements

## Linux

Tested on:

* Linux Mint 22.x
* Ubuntu 24.x

## Thunderbird

* Thunderbird 140 ESR or newer

## Packages

### Debian / Ubuntu / Linux Mint

```bash
sudo apt install \
  python3 \
  python3-gi \
  gir1.2-edataserver-1.2 \
  gir1.2-ebook-1.2 \
  gir1.2-ebookcontacts-1.2
```

---

# Installation

## 1. Extract archive

```bash
unzip eds-contacts-helper.zip
cd eds-contacts-helper
```

## 2. Install helper

```bash
./install-native-helper.sh
```

This installs:

* Native Messaging manifest
* Helper executable
* Thunderbird integration files

---

# Thunderbird Extension

Install the companion extension:

```text
eds-contacts-integration.xpi
```

---

# Testing

## Diagnostics

```bash
~/.local/bin/eds-contacts-helper.py --test diagnostics
```

## List EDS sources

```bash
~/.local/bin/eds-contacts-helper.py --test listSources
```

## List contacts

```bash
~/.local/bin/eds-contacts-helper.py --test listContacts
```

---

# Logs

Logs are stored in:

```text
~/.cache/eds-contacts-helper.log
```

---

# Native Messaging

The helper uses Mozilla Native Messaging.

Installed manifest:

```text
~/.mozilla/native-messaging-hosts/eds_contacts_helper.json
```

---

# Synchronization Model

## EDS → Thunderbird

The helper listens for Evolution Data Server changes and notifies Thunderbird immediately.

## Thunderbird → EDS

The Thunderbird extension sends vCards to the helper through Native Messaging.

---

# Current Status

Experimental but functional.

Implemented:

* EDS → Thunderbird sync
* Thunderbird → EDS sync
* Event-driven updates
* Address book recreation
* vCard conversion
* Native Messaging helper

---

# Known Limitations

* Linux only
* Requires Evolution Data Server
* No automatic helper installation from Thunderbird
* Thunderbird Add-ons store cannot distribute native binaries directly

---

# Security

The helper only accepts connections from explicitly authorized Thunderbird extension IDs through:

```json
"allowed_extensions"
```

inside the Native Messaging manifest.

---

# License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0).

You are free to:

* use
* study
* modify
* redistribute

this software under the terms of the GPL v3 license.

See the LICENSE file for details.

SPDX-License-Identifier: GPL-3.0-only
