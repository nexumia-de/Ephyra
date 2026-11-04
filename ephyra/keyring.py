"""Access token and certificate password in the keyring (phosh_toolkit
keyring: libsecret, in the Flatpak through the Secret portal).
EPHYRA_KEYRING=memory keeps them in memory only, for tests and
screenshots."""
from phosh_toolkit.keyring import CERTIFICATE_PASSWORD, Keyring

TOKEN = "token"

KEYRING = Keyring("de.nexumia.Ephyra",
                  {TOKEN: "Ephyra access token",
                   CERTIFICATE_PASSWORD: "Ephyra client certificate password"},
                  memory_env="EPHYRA_KEYRING")
store = KEYRING.store
lookup = KEYRING.lookup
clear = KEYRING.clear
