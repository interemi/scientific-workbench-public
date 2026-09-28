#!/usr/bin/env python3
"""Tolerant helpers for inspecting iWork .iwa members."""

import re
from collections import Counter
from struct import unpack

try:
    import snappy
    from google.protobuf.internal.decoder import _DecodeVarint32
    from numbers_parser.generated.TSPArchiveMessages_pb2 import ArchiveInfo
    from numbers_parser.generated.mapping import ID_NAME_MAP
    _IWORK_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - optional dependency gate
    snappy = None
    _DecodeVarint32 = None
    ArchiveInfo = None
    ID_NAME_MAP = None
    _IWORK_IMPORT_ERROR = exc


def _require_iwork_deps():
    if _IWORK_IMPORT_ERROR is not None:
        raise RuntimeError(
            "iWork package inspection requires optional dependencies from numbers-parser/snappy. "
            f"Original import error: {_IWORK_IMPORT_ERROR}"
        )


def extract_printable_strings(data, min_len=6, limit=40):
    hints = []
    for raw in re.findall(rb"[ -~]{%d,}" % min_len, data):
        text = raw.decode("utf-8", "ignore").strip()
        if text and text not in hints:
            hints.append(text)
        if len(hints) >= limit:
            break
    return hints


def decompress_iwa_payload(data):
    _require_iwork_deps()
    blocks = []
    while data:
        header = data[:4]
        if len(header) < 4 or header[0] != 0x00:
            break
        length = unpack("<I", bytes(header[1:]) + b"\x00")[0]
        chunk = data[4 : 4 + length]
        data = data[4 + length :]
        try:
            blocks.append(snappy.uncompress(chunk))
        except Exception:
            blocks.append(chunk)
    return b"".join(blocks)


def iter_archive_headers(uncompressed):
    _require_iwork_deps()
    payload = uncompressed
    while payload:
        msg_len, new_pos = _DecodeVarint32(payload, 0)
        cursor = new_pos
        header_bytes = payload[cursor : cursor + msg_len]
        cursor += msg_len
        archive_info = ArchiveInfo.FromString(header_bytes)
        object_entries = []
        for message_info in archive_info.message_infos:
            entry_bytes = payload[cursor : cursor + message_info.length]
            cursor += message_info.length
            klass = ID_NAME_MAP.get(message_info.type)
            pbtype = None
            if klass is not None and hasattr(klass, "DESCRIPTOR"):
                pbtype = klass.DESCRIPTOR.full_name
            object_entries.append(
                {
                    "type_id": int(message_info.type),
                    "pbtype": pbtype,
                    "length": int(message_info.length),
                    "version": list(message_info.version),
                    "strings": extract_printable_strings(entry_bytes, limit=12),
                }
            )
        yield {
            "identifier": str(archive_info.identifier),
            "message_infos": object_entries,
        }
        payload = payload[cursor:]


def inspect_iwa_member(raw_bytes, member_name, max_archives=20):
    _require_iwork_deps()
    uncompressed = decompress_iwa_payload(raw_bytes)
    archives = []
    for archive in iter_archive_headers(uncompressed):
        archives.append(archive)
        if len(archives) >= max_archives:
            break
    type_counter = Counter()
    pbtype_counter = Counter()
    string_hints = []
    for archive in archives:
        for info in archive["message_infos"]:
            type_counter[info["type_id"]] += 1
            if info["pbtype"]:
                pbtype_counter[info["pbtype"]] += 1
            for text in info["strings"]:
                if text not in string_hints:
                    string_hints.append(text)
    return {
        "member_name": member_name,
        "archive_count": len(archives),
        "archives": archives,
        "message_type_counts": {str(key): value for key, value in type_counter.most_common(20)},
        "pbtype_counts": dict(pbtype_counter.most_common(20)),
        "string_hints": string_hints[:40],
    }
