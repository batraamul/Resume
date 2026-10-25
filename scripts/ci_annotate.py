#!/usr/bin/env python3
"""Turn failed tests in a JUnit XML report into GitHub Actions error annotations.

    python scripts/ci_annotate.py build/junit.xml

Annotations show up on the workflow run page and through the checks API, so a failure on
Windows or macOS can be understood without downloading logs. At most ten failures are
reported (GitHub's per-step limit); each message is shortened to the last lines of the traceback.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "build/junit.xml")
    if not path.exists():
        print(f"::error title=No test report::{_escape(f'{path} was not written; the test run did not start.')}")
        return 0
    root = ET.parse(path).getroot()
    failures = []
    for case in root.iter("testcase"):
        for tag in ("failure", "error"):
            node = case.find(tag)
            if node is not None:
                name = f"{case.get('classname', '')}::{case.get('name', '')}"
                detail = (node.text or node.get("message") or "").strip().splitlines()
                failures.append((name, "\n".join(detail[-18:])))
    for name, detail in failures[:10]:
        print(f"::error title={_escape(name)[:200]}::{_escape(detail)[:3500]}")
    if len(failures) > 10:
        print(f"::error title=More failures::{len(failures) - 10} further failure(s) are in the log.")
    total = sum(1 for _ in root.iter("testcase"))
    print(f"::notice title=Test summary::{total} test(s), {len(failures)} failure(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
