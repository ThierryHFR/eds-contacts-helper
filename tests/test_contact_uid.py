import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "eds-contacts-helper.py"
SPEC = importlib.util.spec_from_file_location("eds_contacts_helper", MODULE_PATH)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class FakeFields:
    UID = 42


class FakeEBookContacts:
    ContactField = FakeFields


class ContactWithMethod:
    def get_uid(self):
        return "method-uid"


class ContactWithProperty:
    class Props:
        id = "property-uid"

    props = Props()


class ContactWithField:
    def get(self, field):
        if field == FakeFields.UID:
            return "field-uid"
        return None


class ContactWithPointerLikeMethodAndProperty(ContactWithProperty):
    def get_uid(self):
        return 140123456789456


class ContactWithoutUid:
    pass


class ContactUidTests(unittest.TestCase):
    def test_reads_uid_method(self):
        self.assertEqual(helper._contact_uid(ContactWithMethod()), "method-uid")

    def test_reads_gobject_uid_property(self):
        self.assertEqual(helper._contact_uid(ContactWithProperty()), "property-uid")

    def test_reads_contact_field_uid(self):
        self.assertEqual(
            helper._contact_uid(ContactWithField(), FakeEBookContacts),
            "field-uid",
        )

    def test_ignores_pointer_like_method_value(self):
        self.assertEqual(
            helper._contact_uid(ContactWithPointerLikeMethodAndProperty()),
            "property-uid",
        )

    def test_uses_fallback_only_when_uid_is_unavailable(self):
        self.assertEqual(
            helper._contact_uid(ContactWithoutUid(), FakeEBookContacts, "book:0"),
            "book:0",
        )


if __name__ == "__main__":
    unittest.main()
