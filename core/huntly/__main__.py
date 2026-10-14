"""Entry point for the local core service.

Usage: ``python -m huntly --port 8765`` with ``HUNTLY_API_TOKEN`` set in the environment.
The desktop shell starts this process automatically; running it by hand is for development.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys

import uvicorn

from huntly.api.app import create_app
from huntly.config import get_paths
from huntly.context import AppContext
from huntly.logging_setup import configure_logging
from huntly.scheduler import LocalScheduler
from huntly.security.vault import random_token

log = logging.getLogger("huntly")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="huntly-core")
    parser.add_argument("--port", type=int, default=int(os.environ.get("HUNTLY_PORT", "8765")))
    parser.add_argument("--no-scheduler", action="store_true", help="Disable background jobs")
    parser.add_argument("--log-level", default=os.environ.get("HUNTLY_LOG_LEVEL", "INFO"))
    args = parser.parse_args(argv)

    # Files Huntly creates (database, WAL, logs, documents) are private to this user.
    if sys.platform != "win32":
        os.umask(0o077)
    paths = get_paths()
    configure_logging(paths.logs, args.log_level)

    token = os.environ.pop("HUNTLY_API_TOKEN", None)
    if not token:
        token = random_token()
        # Dev convenience only: the desktop shell always provides its own token.
        print(f"HUNTLY_DEV_TOKEN {token}", flush=True)

    ctx = AppContext(paths)
    ctx.startup()
    if not args.no_scheduler:
        ctx.scheduler = LocalScheduler(ctx)
        ctx.scheduler.start()

    app = create_app(ctx, token)
    # HUNTLY_BIND exists only for the optional container setup; the desktop app always uses loopback.
    host = os.environ.get("HUNTLY_BIND", "127.0.0.1")
    config = uvicorn.Config(app, host=host, port=args.port, log_config=None, access_log=False, server_header=False)
    server = uvicorn.Server(config)

    # Exit cleanly when the parent desktop process goes away.
    parent = os.getppid()

    def _watch_parent():
        import threading
        import time

        def loop():
            while True:
                time.sleep(2)
                if os.getppid() != parent:
                    log.info("parent exited; shutting down")
                    server.should_exit = True
                    return

        threading.Thread(target=loop, daemon=True, name="parent-watch").start()

    if sys.platform != "win32" and os.environ.get("HUNTLY_WATCH_PARENT", "1") == "1":
        _watch_parent()

    signal.signal(signal.SIGTERM, lambda *_: setattr(server, "should_exit", True))
    log.info("core starting", extra={"data": {"port": args.port, "data_dir": str(paths.root)}})
    print(f"HUNTLY_READY {args.port}", flush=True)
    try:
        server.run()
    finally:
        if ctx.scheduler:
            ctx.scheduler.shutdown()
        ctx.vault.lock()
    return 0


if __name__ == "__main__":
    sys.exit(main())
