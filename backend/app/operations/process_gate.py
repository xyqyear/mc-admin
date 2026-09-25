"""Exec only after the owning application has persisted the process identity."""

import os
import sys


def main() -> None:
    gate_fd = int(sys.argv[1])
    try:
        admitted = os.read(gate_fd, 1) == b"1"
    finally:
        os.close(gate_fd)
    if not admitted:
        raise SystemExit(125)
    os.execvpe(sys.argv[2], sys.argv[2:], os.environ)


if __name__ == "__main__":
    main()
