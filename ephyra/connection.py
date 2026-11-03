"""The signed-in account and the route to the server: local address on a
home network, remote address elsewhere (docs/connection.md)."""
import logging

from gi.repository import GObject

from ephyra import keyring, network, route, settings, tasks, tls
from ephyra.api import Jellyfin
from ephyra.http import AUTH, NETWORK, HttpError

log = logging.getLogger("ephyra.connection")

CONNECTING = "connecting"
OFFLINE = "offline"


class Connection(GObject.Object):
    """state: "connecting", "local", "remote" or "offline"."""
    __gsignals__ = {
        "state-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # The server rejected the token: the UI shows the sign-in page.
        "signed-out": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, store=None, watch=True):
        super().__init__()
        self.store = store or settings.Store()
        self.account = self.store.load()
        self.jellyfin = Jellyfin(device_id=self.account.device_id)
        self.state = CONNECTING
        self.error = None            # last HttpError when offline
        self.certificate_error = None
        self._resolving = []         # callbacks waiting for resolve()
        if self.account.signed_in:
            self.jellyfin.token = keyring.lookup(keyring.TOKEN) or ""
            self.jellyfin.user_id = self.account.user_id
        self.load_certificate()
        self.watcher = None
        if watch:
            self.watcher = network.Watcher()
            self.watcher.connect("changed", lambda *_: self.resolve())

    # --- account -----------------------------------------------------

    @property
    def signed_in(self):
        return self.account.signed_in and bool(self.jellyfin.token)

    def load_certificate(self):
        self.certificate_error = None
        self.jellyfin.http.certificate = None
        if not self.account.certificate:
            return
        try:
            data = settings.certificate_path().read_bytes()
            password = keyring.lookup(keyring.CERTIFICATE_PASSWORD)
            self.jellyfin.http.certificate = tls.load(data, password)
        except (OSError, tls.CertificateError) as e:
            self.certificate_error = str(e)
            log.warning("client certificate: %s", e)

    def save(self):
        self.store.save(self.account)

    def signed_in_as(self, result, info):
        """Store the answer of AuthenticateByName."""
        self.account.server_id = info["Id"]
        self.account.server_name = info.get("ServerName", "")
        self.account.user_id = result["User"]["Id"]
        self.account.user_name = result["User"].get("Name", "")
        keyring.store(keyring.TOKEN, result["AccessToken"])
        self.jellyfin.token = result["AccessToken"]
        self.jellyfin.user_id = self.account.user_id
        self.save()

    def sign_out(self, tell_server=True):
        if tell_server and self.jellyfin.token and self.jellyfin.base_url:
            tasks.run(self.jellyfin.sign_out)
        keyring.clear(keyring.TOKEN)
        self.jellyfin.token = ""
        self.account.user_id = ""
        self.save()

    # --- route -------------------------------------------------------

    def candidates(self, ssids):
        return route.candidates(self.account.remote_url, self.account.local_url,
                                self.account.home_networks, ssids)

    def resolve(self, done=None):
        """Find the address to use; done(error) on the main loop."""
        self._resolving.append(done)
        if len(self._resolving) > 1:
            return
        self._set_state(CONNECTING)
        tasks.run(self._probe, self._on_resolved)

    def _probe(self):
        ssids = network.current_ssids()
        error = HttpError(NETWORK, "No server address")
        for kind, url in self.candidates(ssids):
            try:
                info = self.jellyfin.public_info(url, timeout=route.TIMEOUT[kind])
            except HttpError as e:
                log.info("%s %s: %s", kind, url, e)
                # The remote error explains more (certificate, TLS).
                if kind == route.REMOTE or error.kind == NETWORK:
                    error = e
                continue
            if self.account.server_id and info["Id"] != self.account.server_id:
                # Another Jellyfin at the same address: never send our
                # token there.
                log.warning("%s %s is server %s, not ours", kind, url, info["Id"])
                error = HttpError(NETWORK, "A different server answers")
                continue
            return kind, url, info
        raise error

    def _on_resolved(self, result, error):
        if error is None:
            kind, url, info = result
            self.jellyfin.base_url = url
            self.error = None
            if info.get("ServerName") and info["ServerName"] != self.account.server_name:
                self.account.server_name = info["ServerName"]
                self.save()
            self._set_state(kind)
        else:
            self.error = error
            self._set_state(OFFLINE)
        waiting, self._resolving = self._resolving, []
        for done in waiting:
            if done:
                done(error)

    def _set_state(self, state):
        if state != self.state:
            self.state = state
            self.emit("state-changed")

    # --- calls -------------------------------------------------------

    def call(self, fn, done, *args):
        """tasks.run(fn, …) with the route resolved first, one retry
        through a new route after a network error, and "signed-out" on
        401."""
        def attempt(retry):
            def finished(result, error):
                if isinstance(error, HttpError):
                    if error.kind == AUTH:
                        self.sign_out(tell_server=False)
                        self.emit("signed-out")
                    elif error.kind == NETWORK and retry:
                        self.resolve(lambda e: attempt(False)() if e is None
                                     else done(None, e))
                        return
                done(result, error)
            return lambda: tasks.run(fn, finished, *args)

        if not self.jellyfin.base_url:
            self.resolve(lambda e: attempt(True)() if e is None
                         else done(None, e))
        else:
            attempt(True)()


def probe(http, remote_url, local_url, done):
    """Setup: ask both addresses for the server info, through `http` with
    the chosen client certificate. done(result, error) with result
    {"remote": info or HttpError, "local": …}; error only if no address
    answered or they are different servers."""
    jellyfin = Jellyfin(http=http)

    def work():
        answers = {}
        for kind, url in ((route.REMOTE, remote_url), (route.LOCAL, local_url)):
            if not url:
                continue
            try:
                answers[kind] = jellyfin.public_info(url, timeout=route.TIMEOUT[kind])
            except HttpError as e:
                answers[kind] = e
        infos = [a for a in answers.values() if isinstance(a, dict)]
        if not infos:
            errors = list(answers.values())
            # The remote error explains more (certificate, TLS).
            raise errors[0]
        if len({i["Id"] for i in infos}) > 1:
            raise HttpError(NETWORK, "The two addresses are different servers")
        return answers

    tasks.run(work, done)


def sign_in(connection, url, user, password, done):
    """Authenticate at `url`; done(result, error) with result
    (auth answer, server info)."""
    jellyfin = Jellyfin(http=connection.jellyfin.http,
                        device_id=connection.account.device_id)

    def work():
        info = jellyfin.public_info(url)
        jellyfin.base_url = url
        return jellyfin.authenticate(user, password), info

    def finished(result, error):
        if error is None:
            connection.jellyfin.base_url = url
            connection.signed_in_as(*result)
        done(result, error)

    tasks.run(work, finished)

