"""Validate release tags and the complete set of publication destinations."""

import argparse
import json
import re
from pathlib import Path

NUMBER = r"(?:0|[1-9][0-9]*)"
IDENTIFIER = rf"(?:{NUMBER}|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
RELEASE = re.compile(rf"v{NUMBER}\.{NUMBER}\.{NUMBER}(?:-{IDENTIFIER}(?:\.{IDENTIFIER})*)?")


def release_version(tag: str) -> str:
    if not RELEASE.fullmatch(tag):
        raise ValueError("Release tags must be vMAJOR.MINOR.PATCH with an optional SemVer prerelease")
    version = tag[1:]
    if len(version) > 128:
        raise ValueError("Release version exceeds the Docker tag length limit")
    return version


def check_destinations(tag: str, image: str, revision: str, destinations: list[str]) -> None:
    version = release_version(tag)
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Release destinations require the full source revision")
    names = {version, "sha-" + revision[:7]}
    if "-" not in version:
        major, minor, _ = version.split(".")
        names.update({major, f"{major}.{minor}", "latest"})
    expected = {f"{image.lower()}:{name}" for name in names}
    if set(destinations) != expected or len(destinations) != len(expected):
        raise ValueError("Publication destinations differ from the release tag policy")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--tag", required=True)
    validate.add_argument("--github-output", required=True, type=Path)
    check = commands.add_parser("check")
    check.add_argument("--tag", required=True)
    check.add_argument("--image", required=True)
    check.add_argument("--revision", required=True)
    check.add_argument("--tags", required=True)
    args = parser.parse_args()
    if args.command == "validate":
        version = release_version(args.tag)
        with args.github_output.open("a") as output:
            output.write(f"stable={str('-' not in version).lower()}\n")
    else:
        destinations = [value for value in args.tags.splitlines() if value]
        check_destinations(args.tag, args.image, args.revision, destinations)
        print(json.dumps({"destinations": destinations}))


if __name__ == "__main__":
    main()
