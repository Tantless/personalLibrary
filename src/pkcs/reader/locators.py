import re


LOCATOR_PATTERN = re.compile(r"^line\s+(\d+)-(\d+)$")


class LocatorError(ValueError):
    pass


def parse_line_locator(locator: str) -> tuple[int, int]:
    match = LOCATOR_PATTERN.match(locator.strip())
    if match is None:
        raise LocatorError("locator must use format 'line N-M'")
    line_start = int(match.group(1))
    line_end = int(match.group(2))
    if line_start < 1 or line_end < line_start:
        raise LocatorError("locator line range is invalid")
    return line_start, line_end


def format_line_locator(line_start: int, line_end: int) -> str:
    if line_start < 1 or line_end < line_start:
        raise LocatorError("locator line range is invalid")
    return f"line {line_start}-{line_end}"
