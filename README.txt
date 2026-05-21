EDS Contacts Native Messaging helper 1.5.5

Fixes manual vCard serialization for EDS contacts when Python GI exposes BookClient but no contact vCard serializer.

Install:
  ./install-native-helper.sh

Test:
  ~/.local/bin/eds-contacts-helper.py --test diagnostics
  ~/.local/bin/eds-contacts-helper.py --test listContacts
