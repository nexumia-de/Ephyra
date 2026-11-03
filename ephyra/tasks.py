"""Run blocking API calls in worker threads and deliver the result on the
GLib main loop."""
import logging
from concurrent.futures import ThreadPoolExecutor

from gi.repository import GLib

log = logging.getLogger("ephyra.tasks")
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="ephyra")


def run(fn, done=None, *args):
    """Call fn(*args) in a worker; then done(result, error) on the main
    loop, with exactly one of them not None (result may be None too when
    fn returns nothing)."""
    def work():
        try:
            result = fn(*args)
        except Exception as e:  # delivered to the caller, also bugs
            if not hasattr(e, "kind"):
                log.exception("task failed")
            GLib.idle_add(_deliver, done, None, e)
        else:
            GLib.idle_add(_deliver, done, result, None)
    return _pool.submit(work)


def _deliver(done, result, error):
    if done is not None:
        done(result, error)
    return GLib.SOURCE_REMOVE
