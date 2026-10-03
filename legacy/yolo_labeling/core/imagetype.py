"""Sniff an image's format from its first bytes. Replaces `imghdr`.

`imghdr` was deprecated in Python 3.11 and removed in 3.13. Two header parsers
(Statistics, Build Label Cache) used it only to pick which parser to run, so this
reproduces imghdr's own rules -- in imghdr's order -- for exactly the formats they
handle. It is deliberately NOT smarter: a JPEG whose first segment is, say, an ICC
profile is None here because it was None in imghdr, and those callers already
send None to their cv2 fallback.

The rules are Python 3.10's, the version this tool runs on. 3.11 taught imghdr one
more JPEG form (a bare DQT segment, ``\xff\xd8\xff\xdb``); matching that would
quietly change which images skip the header parser on 3.10.
"""

from __future__ import annotations


def sniff(head: bytes) -> str | None:
    """'jpeg', 'png', 'gif', 'bmp', or None -- as `imghdr.what(None, head)` would."""
    if head[6:10] in (b"JFIF", b"Exif"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head.startswith(b"BM"):
        return "bmp"
    return None
