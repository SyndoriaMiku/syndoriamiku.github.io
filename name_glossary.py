"""Safe batch updates for name.cfg."""
from __future__ import annotations

import os
import re
import tempfile
import unicodedata

_CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]')


def normalize_entries(entries):
    normalized = {}
    for cn, vi in entries:
        cn = unicodedata.normalize('NFC', cn.strip())
        vi = unicodedata.normalize('NFC', vi.strip())
        if not cn or not vi:
            continue
        if _CJK.search(vi):
            raise ValueError(f'Bản dịch của “{cn}” vẫn chứa chữ Trung: {vi}')
        if '\n' in cn or '\n' in vi or '=' in cn:
            raise ValueError(f'Tên không hợp lệ: {cn}')
        normalized[cn] = vi
    return normalized


def update_name_cfg(path, entries):
    """Add/update all entries with one read and one atomic file replacement."""
    pending = normalize_entries(entries)
    if not pending:
        return 0
    lines = []
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8', newline='') as stream:
            lines = stream.readlines()
    newline = '\r\n' if any(line.endswith('\r\n') for line in lines) else '\n'
    positions = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            key, _ = stripped.split('=', 1)
            positions[unicodedata.normalize('NFC', key.strip())] = index
    changed = 0
    for cn, vi in pending.items():
        replacement = f'{cn}={vi}{newline}'
        if cn in positions:
            index = positions[cn]
            if lines[index] != replacement:
                lines[index] = replacement
                changed += 1
        else:
            if lines and not lines[-1].endswith('\n'):
                lines[-1] += newline
            positions[cn] = len(lines)
            lines.append(replacement)
            changed += 1
    if not changed:
        return 0
    directory = os.path.dirname(os.path.abspath(path))
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', newline='', delete=False,
                dir=directory, prefix='.name-', suffix='.tmp') as stream:
            temp_path = stream.name
            stream.writelines(lines)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
    return changed
