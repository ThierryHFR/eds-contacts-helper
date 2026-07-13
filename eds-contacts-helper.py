#!/usr/bin/env python3
"""Native Messaging helper for Thunderbird EDS Contacts Integration.
Version 2.0.0: persistent Native Messaging helper with EDS change events.

Can be tested outside Thunderbird:
  ./eds-contacts-helper.py --test ping
  ./eds-contacts-helper.py --test diagnostics
  ./eds-contacts-helper.py --test listContacts
"""

import argparse
import json
import os
import struct
import sys
import traceback
import threading
import time
import hashlib
from datetime import datetime

VERSION = "2.0.0"
LOG_PATH = os.path.expanduser("~/.cache/eds-contacts-helper.log")
WRITE_LOCK = threading.Lock()
WATCH_STATE = {"running": False, "thread": None, "last_hash": None, "interval": 10}


def log(message):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")
    except Exception:
        pass


def read_message():
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) == 0:
        return None
    if len(raw_length) != 4:
        raise RuntimeError("Invalid native message length header")
    message_length = struct.unpack("=I", raw_length)[0]
    if message_length > 64 * 1024 * 1024:
        raise RuntimeError(f"Native message too large: {message_length}")
    data = sys.stdin.buffer.read(message_length)
    if len(data) != message_length:
        raise RuntimeError("Truncated native message")
    return json.loads(data.decode("utf-8"))


def write_message(payload):
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    with WRITE_LOCK:
        sys.stdout.buffer.write(struct.pack("=I", len(encoded)))
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()


def _import_gi(strict=True):
    try:
        import gi
    except Exception as exc:
        raise RuntimeError(
            "python3-gi is missing. Install: sudo apt install python3-gi "
            "gir1.2-edataserver-1.2 gir1.2-ebook-1.2 gir1.2-ebookcontacts-1.2"
        ) from exc

    missing = []
    for namespace in ("EDataServer", "EBookContacts", "EBook"):
        try:
            gi.require_version(namespace, "1.2")
        except Exception as exc:
            missing.append(f"{namespace}: {exc}")
            log(f"MISSING GI namespace {namespace}: {exc}")
    if missing and strict:
        raise RuntimeError("Missing GI namespace(s): " + "; ".join(missing))

    from gi.repository import GLib
    EDataServer = EBookContacts = EBook = None
    try:
        from gi.repository import EDataServer as _EDataServer
        EDataServer = _EDataServer
    except Exception:
        pass
    try:
        from gi.repository import EBookContacts as _EBookContacts
        EBookContacts = _EBookContacts
    except Exception:
        pass
    try:
        from gi.repository import EBook as _EBook
        EBook = _EBook
    except Exception:
        pass
    return EDataServer, EBookContacts, EBook, GLib


def diagnostics():
    data = {"ok": True, "version": VERSION, "logPath": LOG_PATH}
    try:
        EDataServer, EBookContacts, EBook, GLib = _import_gi(strict=False)
        data["namespaces"] = {
            "EDataServer": bool(EDataServer),
            "EBookContacts": bool(EBookContacts),
            "EBook": bool(EBook),
        }
        data["EBook_classes"] = [n for n in ("BookClient", "Client") if EBook and hasattr(EBook, n)]
        data["EBookContact_classes"] = [n for n in ("Contact", "EContact", "VCard") if EBookContacts and hasattr(EBookContacts, n)]
        if EDataServer:
            registry = EDataServer.SourceRegistry.new_sync(None)
            sources = list(registry.list_sources(EDataServer.SOURCE_EXTENSION_ADDRESS_BOOK))
            data["sources"] = [_source_summary(s) for s in sources]
    except Exception as exc:
        data["ok"] = False
        data["error"] = str(exc)
        data["traceback"] = traceback.format_exc()
    log("DIAGNOSTICS " + json.dumps(data, ensure_ascii=False))
    return data


def _get_registry_and_sources():
    EDataServer, EBookContacts, EBook, GLib = _import_gi(strict=True)
    registry = EDataServer.SourceRegistry.new_sync(None)
    sources = list(registry.list_sources(EDataServer.SOURCE_EXTENSION_ADDRESS_BOOK))
    enabled = []
    for source in sources:
        try:
            if hasattr(source, "get_enabled") and not source.get_enabled():
                continue
        except Exception:
            pass
        enabled.append(source)
    log(f"Found {len(sources)} EDS address book source(s), {len(enabled)} enabled")
    for s in enabled:
        log("SOURCE " + json.dumps(_source_summary(s), ensure_ascii=False))
    return EDataServer, EBookContacts, EBook, GLib, registry, enabled


def _source_label(source):
    try:
        return source.get_display_name() or source.get_uid()
    except Exception:
        return "unknown-source"


def _source_summary(source):
    d = {"label": _source_label(source)}
    for name in ("get_uid", "get_parent", "get_enabled"):
        try:
            d[name[4:]] = getattr(source, name)()
        except Exception:
            pass
    return d


def _open_client(EBook, source):
    candidates = []
    for class_name in ("BookClient", "Client"):
        klass = getattr(EBook, class_name, None)
        if klass is not None:
            candidates.append((class_name, klass))
    log("EBook client candidates: " + (", ".join(n for n, _ in candidates) or "none"))

    errors = []
    for class_name, klass in candidates:
        connect_sync = getattr(klass, "connect_sync", None)
        if connect_sync is None:
            errors.append(f"{class_name}.connect_sync missing")
            continue
        for args in ((source, 30, None), (source, None)):
            try:
                result = connect_sync(*args)
                values = result if isinstance(result, tuple) else (result,)
                for item in values:
                    if item is not None and (hasattr(item, "get_contacts_sync") or hasattr(item, "add_contact_sync")):
                        log(f"Connected EDS client via {class_name}.connect_sync")
                        return item
                errors.append(f"{class_name}.connect_sync returned no client: {result!r}")
            except Exception as exc:
                errors.append(f"{class_name}.connect_sync{args!r}: {exc}")
    raise RuntimeError("No supported EBook client binding found. " + "; ".join(errors))


def _query_candidates(EBookContacts):
    # On Linux Mint/Ubuntu Noble, EBook.BookClient.get_contacts_sync expects
    # a raw S-expression string, not an EBookContacts.BookQuery object.
    # Keep BookQuery only as an optional source of a string, and never return
    # non-string query objects.
    candidates = []
    for sexp in (
        "",
        "#t",
        "(contains \"full_name\" \"\")",
        "(exists \"full_name\")",
        "(contains \"email\" \"@\")",
    ):
        candidates.append(sexp)
    try:
        q = EBookContacts.BookQuery.any_field_contains("")
        if hasattr(q, "to_string"):
            qs = q.to_string()
        else:
            qs = str(q)
        if isinstance(qs, str) and qs and not qs.startswith("<") and qs not in candidates:
            candidates.append(qs)
    except Exception as exc:
        log(f"BookQuery.any_field_contains skipped: {exc}")
    return candidates



def _clean_text(value):
    """Return a real text value, ignoring GI pointer-like integers."""
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", "replace")
        except Exception:
            return None
    if isinstance(value, int):
        # Some GI EContact get/get_const calls expose gpointer addresses for
        # string fields. Those are not usable contact values.
        return None
    text = str(value).strip()
    if not text or text.lower() in ("none", "null"):
        return None
    # Ignore plain pointer-looking decimal values.
    if text.isdigit() and len(text) >= 6:
        return None
    return text

_FIELD_TO_PROP = {
    # E_CONTACT_UID is exposed as the GObject property "id" by libebook.
    "UID": "id",
    "FULL_NAME": "full_name", "FN": "full_name",
    "NICKNAME": "nickname",
    "FAMILY_NAME": "family_name", "NAME_FAMILY": "family_name",
    "GIVEN_NAME": "given_name", "NAME_GIVEN": "given_name",
    "EMAIL": "email", "EMAIL_1": "email_1", "EMAIL_2": "email_2", "EMAIL_3": "email_3", "EMAIL_4": "email_4",
    "TEL": "phone", "PHONE": "phone", "PRIMARY_PHONE": "primary_phone",
    "HOME_PHONE": "home_phone", "WORK_PHONE": "business_phone", "MOBILE_PHONE": "mobile_phone",
}

def _prop_value(contact, prop_name):
    for obj in (getattr(contact, "props", None), contact):
        if obj is None:
            continue
        try:
            value = getattr(obj, prop_name)
            cleaned = _clean_text(value)
            if cleaned:
                return cleaned
            if isinstance(value, (list, tuple)):
                cleaned_items = [_clean_text(v) for v in value]
                cleaned_items = [v for v in cleaned_items if v]
                if cleaned_items:
                    return cleaned_items
        except Exception:
            pass
    return None


def _contact_uid(contact, EBookContacts=None, fallback=None):
    """Return the stable EDS UID across the different GI binding shapes.

    Some libebook GIR versions do not expose ``get_uid()`` even though the
    UID is available through the GObject ``id`` property or ContactField.
    Falling back to a list index in that situation changes the identity of a
    contact whenever the address book order changes and breaks sync mapping.
    """
    for name in ("get_uid", "get_id"):
        try:
            value = _clean_text(getattr(contact, name)())
            if value:
                return value
        except Exception:
            pass

    # libebook exposes E_CONTACT_UID as the GObject property "id".  Keep
    # "uid" as a compatibility fallback for alternate/older bindings.
    for property_name in ("id", "uid"):
        value = _prop_value(contact, property_name)
        if value:
            return value

    if EBookContacts is not None:
        field = _field_enum(EBookContacts, "UID")
        if field is not None:
            for method_name in ("get", "get_const"):
                try:
                    value = _clean_text(getattr(contact, method_name)(field))
                    if value:
                        return value
                except Exception:
                    pass
    return fallback


def _vcard_escape(value):
    if value is None:
        return ""
    value = str(value)
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )


def _first_nonempty(values):
    for value in values:
        if value:
            if isinstance(value, (list, tuple)):
                for item in value:
                    if item:
                        return item
            else:
                return value
    return None


def _field_enum(EBookContacts, *names):
    enum = getattr(EBookContacts, "ContactField", None)
    if enum is None:
        return None
    for name in names:
        try:
            return getattr(enum, name)
        except Exception:
            pass
    return None


def _contact_field(contact, EBookContacts, *field_names):
    # Prefer GObject properties. On some GI versions EContact.get/get_const
    # returns raw pointer-like integers for string fields, while props expose
    # proper Python strings.
    for field_name in field_names:
        prop_name = _FIELD_TO_PROP.get(field_name)
        if prop_name:
            value = _prop_value(contact, prop_name)
            if value:
                return value

    field = _field_enum(EBookContacts, *field_names)
    if field is not None:
        for method_name in ("get", "get_const"):
            try:
                method = getattr(contact, method_name)
                value = method(field)
                cleaned = _clean_text(value)
                if cleaned:
                    return cleaned
            except Exception:
                pass
    # Method fallbacks used by some GI versions.
    lowered = [n.lower() for n in field_names]
    method_candidates = []
    for n in lowered:
        method_candidates.extend([
            "get_" + n.lower(),
            "get_" + n.lower().replace("_", ""),
        ])
    for method_name in method_candidates:
        try:
            method = getattr(contact, method_name)
            value = method()
            cleaned = _clean_text(value)
            if cleaned:
                return cleaned
        except Exception:
            pass
    return None


def _contact_emails(contact, EBookContacts):
    emails = []
    # First try the email list property, then individual email_N properties.
    prop_email = _prop_value(contact, "email")
    if prop_email:
        seq = prop_email if isinstance(prop_email, (list, tuple)) else [prop_email]
        for item in seq:
            cleaned = _clean_text(item)
            if cleaned and cleaned not in emails:
                emails.append(cleaned)
    for method_name in ("get_email_addresses", "get_emails"):
        try:
            values = getattr(contact, method_name)()
            if values:
                for value in values:
                    cleaned = _clean_text(value)
                    if cleaned and cleaned not in emails:
                        emails.append(cleaned)
        except Exception:
            pass
    for names in (("EMAIL_1",), ("EMAIL_2",), ("EMAIL_3",), ("EMAIL_4",)):
        value = _contact_field(contact, EBookContacts, *names)
        if value:
            seq = value if isinstance(value, (list, tuple)) else [value]
            for item in seq:
                cleaned = _clean_text(item)
                if cleaned and cleaned not in emails:
                    emails.append(cleaned)
    return emails


def _contact_vcard(contact, EBookContacts=None, uid=None):
    # Prefer native serialization when the binding supports it.
    for name in ("to_string", "get_vcard_string", "get_vcard"):
        try:
            value = getattr(contact, name)()
            if value:
                value = str(value)
                if "BEGIN:VCARD" in value:
                    return value
        except Exception:
            pass

    # Some EDS GIR versions expose contacts but do not expose a vCard serializer.
    # Build a conservative vCard manually from common EContact fields.
    full_name = None
    family = None
    given = None
    nickname = None
    if EBookContacts is not None:
        full_name = _contact_field(contact, EBookContacts, "FULL_NAME", "FN")
        nickname = _contact_field(contact, EBookContacts, "NICKNAME")
        family = _contact_field(contact, EBookContacts, "FAMILY_NAME", "NAME_FAMILY")
        given = _contact_field(contact, EBookContacts, "GIVEN_NAME", "NAME_GIVEN")

    try:
        name_obj = contact.get_name()
        for attr_name, target in (("family", "family"), ("given", "given"), ("additional", "additional")):
            try:
                value = _clean_text(getattr(name_obj, attr_name))
                if value and target == "family" and not family:
                    family = value
                if value and target == "given" and not given:
                    given = value
            except Exception:
                pass
    except Exception:
        pass

    emails = _contact_emails(contact, EBookContacts) if EBookContacts is not None else []
    uid = uid or _contact_uid(contact, EBookContacts) or ""
    fn = full_name or " ".join([str(given or "").strip(), str(family or "").strip()]).strip() or nickname or (emails[0] if emails else uid) or "EDS Contact"

    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        "UID:" + _vcard_escape(uid),
        "FN:" + _vcard_escape(fn),
        "N:" + _vcard_escape(family or "") + ";" + _vcard_escape(given or "") + ";;;",
    ]
    if nickname:
        lines.append("NICKNAME:" + _vcard_escape(nickname))
    for email in emails:
        lines.append("EMAIL;TYPE=INTERNET:" + _vcard_escape(email))
    lines.append("END:VCARD")
    log(f"Manual vCard serialization used emails={len(emails)}")
    return "\r\n".join(lines) + "\r\n"


def _get_contacts_from_client(client, EBookContacts):
    errors = []
    if hasattr(client, "get_contacts_sync"):
        for query in _query_candidates(EBookContacts):
            try:
                log(f"Trying get_contacts_sync query={query!r} type={type(query).__name__}")
                result = client.get_contacts_sync(query, None)
                if isinstance(result, tuple):
                    if result and result[0] is False:
                        errors.append(f"query {query!r}: returned false")
                        continue
                    for item in result:
                        if isinstance(item, (list, tuple)):
                            return list(item), query
                    if len(result) >= 2:
                        return list(result[1] or []), query
                elif isinstance(result, (list, tuple)):
                    return list(result), query
            except Exception as exc:
                errors.append(f"query {query!r}: {exc}")
    raise RuntimeError("No working get_contacts_sync binding/query. " + "; ".join(errors))


def list_contacts():
    EDataServer, EBookContacts, EBook, GLib, registry, sources = _get_registry_and_sources()
    contacts = []
    errors = []
    for source in sources:
        label = _source_label(source)
        try:
            client = _open_client(EBook, source)
            raw_contacts, query = _get_contacts_from_client(client, EBookContacts)
            log(f"listContacts source={label} query={query!r} count={len(raw_contacts or [])}")
            for idx, contact in enumerate(raw_contacts or []):
                fallback_uid = f"{source.get_uid()}:{idx}"
                uid = _contact_uid(contact, EBookContacts, fallback=fallback_uid)
                if uid == fallback_uid:
                    log(f"WARNING contact has no readable EDS UID; using unstable fallback {fallback_uid}")
                contacts.append({"uid": uid, "vcard": _contact_vcard(contact, EBookContacts, uid), "source": label})
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            log(f"ERROR listContacts source={label}: {exc}\n{traceback.format_exc()}")
    return {"ok": True, "contacts": contacts, "count": len(contacts), "errors": errors}


def _new_contact_from_vcard(EBookContacts, vcard):
    for class_name in ("Contact", "EContact"):
        klass = getattr(EBookContacts, class_name, None)
        if klass:
            for meth in ("new_from_vcard", "new_from_vcard_with_uid"):
                fn = getattr(klass, meth, None)
                if fn:
                    try:
                        return fn(vcard)
                    except TypeError:
                        pass
    raise RuntimeError("No supported EBookContacts contact-from-vCard binding found")


def _pick_writable_source(sources):
    if not sources:
        raise RuntimeError("No EDS address book source found")
    for source in sources:
        name = (_source_label(source) or "").lower()
        if any(token in name for token in ("personal", "personnel", "contacts", "address")):
            return source
    return sources[0]


def add_contact(vcard):
    if not vcard or not isinstance(vcard, str):
        raise RuntimeError("addContact requires a vcard string")
    EDataServer, EBookContacts, EBook, GLib, registry, sources = _get_registry_and_sources()
    source = _pick_writable_source(sources)
    label = _source_label(source)
    client = _open_client(EBook, source)
    contact = _new_contact_from_vcard(EBookContacts, vcard)
    uid = None
    opflags = 0
    try:
        opflags = getattr(getattr(EBook, "OperationFlags", None), "NONE", 0)
    except Exception:
        opflags = 0
    cancellables = [None]
    try:
        cancellables.append(GLib.Cancellable.new())
    except Exception:
        pass

    def _call_first_working(method, argsets):
        last_exc = None
        for args in argsets:
            try:
                log(f"Trying {method.__name__} args={len(args)}")
                return method(*args)
            except Exception as exc:
                last_exc = exc
                log(f"{method.__name__} failed with {len(args)} arg(s): {exc}")
        raise last_exc or RuntimeError("No argument form tried")

    if hasattr(client, "add_contact_sync"):
        method = client.add_contact_sync
        argsets = []
        for cancellable in cancellables:
            argsets.append((contact, opflags, cancellable))
        argsets.append((contact, opflags))
        argsets.append((contact,))
        result = _call_first_working(method, argsets)
    elif hasattr(client, "create_contact_sync"):
        method = client.create_contact_sync
        argsets = []
        for cancellable in cancellables:
            argsets.append((contact, cancellable))
        argsets.append((contact,))
        result = _call_first_working(method, argsets)
    else:
        raise RuntimeError("No supported add/create contact binding found")
    values = result if isinstance(result, tuple) else (result,)
    for item in values:
        if isinstance(item, str) and item:
            uid = item
    uid = uid or _contact_uid(contact, EBookContacts) or "unknown-uid"
    log(f"Added contact to EDS source={label}")
    return {"ok": True, "uid": uid, "source": label}



def _contacts_signature(contacts_payload):
    contacts = contacts_payload.get("contacts") or []
    compact = []
    for c in contacts:
        compact.append({"uid": c.get("uid"), "vcard": c.get("vcard")})
    compact.sort(key=lambda x: x.get("uid") or "")
    raw = json.dumps(compact, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest(), len(compact)


def _watch_loop(interval):
    log(f"WATCH loop started interval={interval}s")
    while WATCH_STATE.get("running"):
        try:
            payload = list_contacts()
            sig, count = _contacts_signature(payload)
            if WATCH_STATE.get("last_hash") is None:
                WATCH_STATE["last_hash"] = sig
                log(f"WATCH initial snapshot count={count} hash={sig}")
            elif sig != WATCH_STATE.get("last_hash"):
                WATCH_STATE["last_hash"] = sig
                log(f"WATCH detected EDS change count={count} hash={sig}")
                write_message({"event": "edsChanged", "reason": "contactsChanged", "count": count})
        except Exception as exc:
            log(f"WATCH error {exc}\n{traceback.format_exc()}")
            try:
                write_message({"event": "watchError", "error": str(exc)})
            except Exception:
                pass
        time.sleep(max(5, int(interval or 10)))
    log("WATCH loop stopped")


def start_watch(interval_seconds=10):
    interval = max(5, int(interval_seconds or 10))
    WATCH_STATE["interval"] = interval
    if WATCH_STATE.get("running") and WATCH_STATE.get("thread") and WATCH_STATE["thread"].is_alive():
        return {"ok": True, "event": "watchStarted", "intervalSeconds": interval, "alreadyRunning": True}
    WATCH_STATE["running"] = True
    WATCH_STATE["last_hash"] = None
    t = threading.Thread(target=_watch_loop, args=(interval,), daemon=True)
    WATCH_STATE["thread"] = t
    t.start()
    return {"ok": True, "event": "watchStarted", "intervalSeconds": interval}


def handle(message):
    action = (message or {}).get("action")
    if action == "ping":
        return {"ok": True, "version": VERSION}
    if action == "diagnostics":
        return diagnostics()
    if action == "listSources":
        d = diagnostics()
        return {"ok": d.get("ok", False), "sources": d.get("sources", []), "error": d.get("error")}
    if action == "listContacts":
        return list_contacts()
    if action == "addContact":
        return add_contact(message.get("vcard"))
    if action == "watch":
        return start_watch(message.get("intervalSeconds", 10))
    return {"ok": False, "error": f"Unknown action: {action}"}


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--test", choices=["ping", "diagnostics", "listSources", "listContacts"], help="Run action directly without Native Messaging framing")
    args, _unknown = parser.parse_known_args()
    if _unknown:
        log("Ignoring Native Messaging argv: " + " ".join(_unknown))
    try:
        if args.test:
            payload = handle({"action": args.test})
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if payload.get("ok") else 1
        while True:
            message = read_message()
            if message is None:
                WATCH_STATE["running"] = False
                return 0
            log(f"REQUEST {message.get('action')}")
            response = handle(message)
            if isinstance(message, dict) and message.get("requestId") is not None:
                response["requestId"] = message.get("requestId")
            write_message(response)
    except Exception as exc:
        log(f"FATAL {exc}\n{traceback.format_exc()}")
        if args.test:
            print(json.dumps({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}, ensure_ascii=False, indent=2))
        else:
            try:
                write_message({"ok": False, "error": str(exc)})
            except Exception:
                pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
