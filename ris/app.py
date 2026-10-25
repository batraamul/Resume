"""Application entry point and lifecycle."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from ris import APP_NAME, __version__

log = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="resume-intelligence-studio", description=f"{APP_NAME} {__version__}")
    p.add_argument("--version", action="store_true", help="print the version and exit")
    p.add_argument("--selftest", action="store_true", help="check the installation and exit")
    p.add_argument("--report", metavar="FILE",
                   help="also write --version / --selftest output to FILE (useful on Windows, where the "
                        "windowed application has no console)")
    p.add_argument("--data-dir", help="use this data folder (overrides the default location)")
    p.add_argument("--sample", action="store_true", help="open the fictional sample workspace")
    p.add_argument("--verbose", action="store_true", help="also log to the console")
    p.add_argument("--screenshot", help=argparse.SUPPRESS)  # developer: render the main window to a PNG and exit
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    lines: list[str] = []

    def out(text: str) -> None:
        lines.append(text)
        try:
            print(text, flush=True)
        except (OSError, AttributeError, ValueError):  # no console attached (windowed build)
            pass

    def write_report() -> None:
        if args.report:
            with open(args.report, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")

    if args.version:
        out(f"{APP_NAME} {__version__}")
        write_report()
        return 0
    if args.data_dir:
        os.environ["RIS_DATA_DIR"] = os.path.abspath(os.path.expanduser(args.data_dir))
    from ris.config import AppConfig
    from ris.logging_setup import configure_logging
    from ris.security.tempfiles import cleanup_stale

    cfg = AppConfig.load()
    configure_logging(cfg.resolved_data_dir() / "logs", cfg.log_level, console=args.verbose)
    log.info("Starting %s %s", APP_NAME, __version__)
    cleanup_stale()
    if args.selftest:
        from ris.selftest import run

        code = run(out)
        write_report()
        return code
    from ris.ui.application import run_gui

    return run_gui(cfg, open_sample=args.sample, screenshot=args.screenshot)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
