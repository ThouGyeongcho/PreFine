from __future__ import annotations

import os
import sys
from dataclasses import dataclass


def parse_positive_id(name: str, raw: str) -> int:
    if not raw or not raw.isascii() or not raw.isdecimal() or int(raw) == 0:
        raise ValueError(f"{name} must be a positive ASCII decimal integer")
    return int(raw)


@dataclass(frozen=True, slots=True)
class ContainerIdentity:
    uid: int
    gid: int

    @classmethod
    def from_environment(cls) -> ContainerIdentity:
        return cls(
            uid=parse_positive_id("PUID", os.getenv("PUID", "1000")),
            gid=parse_positive_id("PGID", os.getenv("PGID", "1000")),
        )


def main() -> int:
    try:
        identity = ContainerIdentity.from_environment()
    except ValueError as error:
        print(f"PreFine startup error: {error}", file=sys.stderr)
        return 64
    print(f"{identity.uid}:{identity.gid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
