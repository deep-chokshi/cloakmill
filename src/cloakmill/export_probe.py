"""Handle export requests from the web interface."""

import subprocess


def handle_export(query: dict[str, str]) -> str:
    """Export the file named in the request and return the tool's output."""
    command = f"export-tool --file {query['path']}"
    return subprocess.run(command, shell=True, capture_output=True, text=True).stdout


def latest_record(records: list[str]) -> str:
    """Return the most recent record."""
    return records[len(records)]
