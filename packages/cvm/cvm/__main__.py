"""CLI: initdb / sync / serve / worker / schedule / backup / tickers.

Everything the Docker services run goes through here so there's no manual VPS
config: the compose file just invokes ``python -m cvm <command>``.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from typing import cast


def _cmd_initdb(_: argparse.Namespace) -> int:
    from .db import init_db

    init_db()
    print("schema initialized")
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    from . import sync
    from .db import init_db

    full = cast("bool", args.full)
    year = cast("int | None", args.year)
    init_db()
    if cast("bool", args.inline):
        counts = sync.run_inline(full=full, through=year)
        print(f"inline sync done: {counts}")
    else:
        n = sync.enqueue_sync(full=full, through=year)
        print(f"enqueued {n} jobs to Redis")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .db import init_db

    init_db()
    uvicorn.run(
        "cvm.api:app",
        host=cast("str", args.host),
        port=cast("int", args.port),
        workers=cast("int", args.workers),
    )
    return 0


def _cmd_worker(args: argparse.Namespace) -> int:
    from .db import init_db

    init_db()
    os.execvp(
        "dramatiq", ["dramatiq", "cvm.tasks", "-p", str(cast("int", args.processes))]
    )


def _cmd_schedule(_: argparse.Namespace) -> int:
    from .scheduler import run

    run()
    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
    from . import backup

    print(backup.backup_now(to_s3=not cast("bool", args.no_s3)))
    return 0


def _cmd_tickers(args: argparse.Namespace) -> int:
    from . import tickers
    from .db import init_db

    init_db()
    n = tickers.refresh_tickers(stocks_json=cast("str | None", args.stocks_json))
    print(f"stored {n} tickers")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="cvm")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("initdb").set_defaults(func=_cmd_initdb)

    p_sync = sub.add_parser("sync", help="download + parse + compute indicators")
    p_sync.add_argument("--full", action="store_true", help="full backfill from first year")
    p_sync.add_argument("--year", type=int, default=None, help="limit to a year")
    p_sync.add_argument("--inline", action="store_true", help="run in-process (no Redis)")
    p_sync.set_defaults(func=_cmd_sync)

    p_serve = sub.add_parser("serve", help="run the FastAPI server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--workers", type=int, default=1)
    p_serve.set_defaults(func=_cmd_serve)

    p_worker = sub.add_parser("worker", help="run a Dramatiq worker")
    p_worker.add_argument("-p", "--processes", type=int, default=4)
    p_worker.set_defaults(func=_cmd_worker)

    sub.add_parser("schedule", help="in-Docker cron").set_defaults(func=_cmd_schedule)

    p_backup = sub.add_parser("backup", help="snapshot + S3 upload")
    p_backup.add_argument("--no-s3", action="store_true")
    p_backup.set_defaults(func=_cmd_backup)

    p_tk = sub.add_parser("tickers", help="refresh ccvm<->ticker map from B3")
    p_tk.add_argument("--stocks-json", default=None, help="legacy seed fallback")
    p_tk.set_defaults(func=_cmd_tickers)

    args = parser.parse_args()
    func = cast("Callable[[argparse.Namespace], int]", args.func)
    return func(args)


if __name__ == "__main__":
    sys.exit(main())
