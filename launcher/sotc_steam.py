#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Steam non-Steam shortcut and artwork installer for Shadow of the Colossus.

Reads and writes Steam's binary ``userdata/<id>/config/shortcuts.vdf`` without third-party VDF
libraries, computes Steam's deterministic shortcut AppID, and installs cover/hero/grid/icon artwork
from the user's PS4 dump (``sce_sys/icon0.png`` and ``sce_sys/pic1.png``) when available.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import struct
import zlib

TYPE_MAP = 0x00
TYPE_STR = 0x01
TYPE_INT = 0x02
TYPE_END = 0x08

GRID_SPECS = (
    # (filename suffix, preferred source key, target size or None for original aspect)
    ('_icon.png', 'icon', None),
    ('.png', 'art', (920, 430)),
    ('p.png', 'art', (600, 900)),
    ('_hero.png', 'art', (1920, 620)),
)


def _read_cstring(data: bytes, pos: int) -> tuple[str, int]:
    end = data.find(b'\x00', pos)
    if end < 0:
        raise ValueError(f'unterminated VDF string at offset {pos}')
    return data[pos:end].decode('utf-8', errors='replace'), end + 1


def _parse_map(data: bytes, pos: int) -> tuple[dict, int]:
    out = {}
    length = len(data)
    while pos < length:
        tag = data[pos]
        pos += 1
        if tag == TYPE_END:
            return out, pos
        key, pos = _read_cstring(data, pos)
        if tag == TYPE_MAP:
            val, pos = _parse_map(data, pos)
            out[key] = val
        elif tag == TYPE_STR:
            val, pos = _read_cstring(data, pos)
            out[key] = val
        elif tag == TYPE_INT:
            if pos + 4 > length:
                raise ValueError(f'truncated VDF uint32 for key {key!r} at offset {pos}')
            (val,) = struct.unpack_from('<I', data, pos)
            pos += 4
            out[key] = val
        else:
            raise ValueError(f'unsupported VDF tag 0x{tag:02x} for key {key!r} at offset {pos - 1}')
    return out, pos


def parse_vdf(data: bytes) -> dict:
    """Parse Steam's binary shortcuts.vdf payload into a nested Python dict."""
    if not data:
        return {'shortcuts': {}}
    parsed, _ = _parse_map(data, 0)
    if 'shortcuts' not in parsed or not isinstance(parsed['shortcuts'], dict):
        parsed.setdefault('shortcuts', {})
    return parsed


def _dump_map(out: bytearray, mapping: dict) -> None:
    for key, value in mapping.items():
        key_bytes = str(key).encode('utf-8') + b'\x00'
        if isinstance(value, dict):
            out.append(TYPE_MAP)
            out.extend(key_bytes)
            _dump_map(out, value)
        elif isinstance(value, bool) or isinstance(value, int):
            out.append(TYPE_INT)
            out.extend(key_bytes)
            out.extend(struct.pack('<I', int(value) & 0xffffffff))
        else:
            out.append(TYPE_STR)
            out.extend(key_bytes)
            out.extend(str('' if value is None else value).encode('utf-8'))
            out.append(0)
    out.append(TYPE_END)


def dump_vdf(obj: dict) -> bytes:
    """Serialize a nested Python dict back into Steam's binary shortcuts.vdf format."""
    out = bytearray()
    _dump_map(out, obj)
    return bytes(out)


def steam_shortcut_appid(exe: str, app_name: str) -> int:
    """Return Steam's unsigned 32-bit non-Steam AppID for ``(Exe, AppName)``."""
    payload = (str(exe) + str(app_name)).encode('utf-8')
    return (zlib.crc32(payload) | 0x80000000) & 0xffffffff


def _ensure_quoted(value: str) -> str:
    text = str(value).strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text
    return f'"{text}"'


def steam_launch_spec(is_windows: bool, frozen: bool, appimage_path: str, executable: str,
                      port_dir: str | Path) -> tuple[str, str, str]:
    """Build quoted ``(Exe, StartDir, LaunchOptions)`` for a direct ``--play`` Steam shortcut."""
    port = Path(port_dir)
    if not is_windows and appimage_path:
        exe = Path(appimage_path)
        return _ensure_quoted(str(exe)), _ensure_quoted(str(exe.parent)), '--play'
    if frozen:
        exe = Path(executable)
        return _ensure_quoted(str(exe)), _ensure_quoted(str(port)), '--play'
    exe = Path(executable)
    launcher_py = port / 'launcher' / 'sotc_launcher_win.py'
    return _ensure_quoted(str(exe)), _ensure_quoted(str(port)), f'"{launcher_py}" --play'


def find_steam_userdata_dirs(home: Path | None = None, is_windows: bool | None = None,
                             env: dict[str, str] | None = None) -> list[Path]:
    """Discover per-account Steam ``userdata/<id>`` directories, deduplicated via real path."""
    if is_windows is None:
        is_windows = os.name == 'nt'
    environ = os.environ if env is None else env
    base_home = Path.home() if home is None else Path(home)

    if is_windows:
        roots = [
            Path(environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Steam' / 'userdata',
            Path(environ.get('PROGRAMFILES', r'C:\Program Files')) / 'Steam' / 'userdata',
        ]
    else:
        roots = [
            base_home / '.local' / 'share' / 'Steam' / 'userdata',
            base_home / '.steam' / 'steam' / 'userdata',
            base_home / '.var' / 'app' / 'com.valvesoftware.Steam' / '.local' / 'share' / 'Steam' / 'userdata',
        ]

    seen_roots: set[Path] = set()
    seen_users: set[Path] = set()
    users: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            resolved_root = root.resolve()
        except OSError:
            resolved_root = root
        if resolved_root in seen_roots:
            continue
        seen_roots.add(resolved_root)
        try:
            children = sorted(root.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for child in children:
            if not (child.is_dir() and child.name.isdigit() and child.name != '0'):
                continue
            try:
                resolved_child = child.resolve()
            except OSError:
                resolved_child = child
            if resolved_child in seen_users:
                continue
            seen_users.add(resolved_child)
            users.append(child)
    return sorted(users, key=lambda p: str(p))


def _save_fitted_png(src: Path, dst: Path, size: tuple[int, int] | None) -> None:
    try:
        from PIL import Image, ImageOps
        with Image.open(src) as image:
            converted = image.convert('RGBA')
            if size is not None:
                resampling = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', Image.LANCZOS)
                converted = ImageOps.fit(converted, size, method=resampling)
            converted.save(dst, format='PNG')
            return
    except (ImportError, OSError, ValueError):
        pass
    shutil.copy2(src, dst)


def install_steam_artwork(grid_dir: Path, appid_u32: int, game_dir: str | Path | None = None,
                          fallback_icon: str | Path | None = None) -> tuple[Path | None, list[Path]]:
    """Copy or resize PS4 dump artwork (``icon0.png``, ``pic1.png``) into Steam's ``grid/`` folder."""
    icon_src: Path | None = None
    art_src: Path | None = None

    if game_dir:
        sce_sys = Path(game_dir) / 'sce_sys'
        candidate_icon = sce_sys / 'icon0.png'
        candidate_pic1 = sce_sys / 'pic1.png'
        if candidate_icon.is_file():
            icon_src = candidate_icon
        if candidate_pic1.is_file():
            art_src = candidate_pic1

    if icon_src is None and fallback_icon:
        fallback = Path(fallback_icon)
        if fallback.is_file():
            icon_src = fallback

    if art_src is None:
        art_src = icon_src
    if icon_src is None:
        icon_src = art_src

    if icon_src is None and art_src is None:
        return None, []

    grid_dir.mkdir(parents=True, exist_ok=True)
    sources = {'icon': icon_src, 'art': art_src}
    created: list[Path] = []
    icon_dst: Path | None = None
    for suffix, src_key, size in GRID_SPECS:
        src = sources[src_key]
        if src is None or not src.is_file():
            continue
        dst = grid_dir / f'{appid_u32}{suffix}'
        _save_fitted_png(src, dst, size)
        created.append(dst)
        if suffix == '_icon.png':
            icon_dst = dst
    return icon_dst, created


def _matching_shortcut_key(shortcuts: dict, app_name: str) -> str | None:
    target = app_name.strip().lower()
    for key, entry in shortcuts.items():
        if not isinstance(entry, dict):
            continue
        name = entry.get('AppName') or entry.get('appname') or ''
        if str(name).strip().lower() == target:
            return str(key)
    return None


def add_to_steam(exe: str, start_dir: str, launch_options: str = '--play',
                 app_name: str = 'Shadow of the Colossus',
                 game_dir: str | Path | None = None,
                 fallback_icon: str | Path | None = None,
                 userdata_dirs: list[Path] | None = None) -> dict:
    """Register or update Shadow of the Colossus in Steam's ``shortcuts.vdf`` and install grid artwork."""
    dirs = list(userdata_dirs) if userdata_dirs is not None else find_steam_userdata_dirs()
    if not dirs:
        return {'updated': [], 'artwork': [], 'appid': 0}

    exe_q = _ensure_quoted(exe)
    start_q = _ensure_quoted(start_dir)
    appid_u32 = steam_shortcut_appid(exe_q, app_name)

    updated: list[Path] = []
    all_artwork: list[Path] = []
    for user_dir in dirs:
        config_dir = Path(user_dir) / 'config'
        vdf_path = config_dir / 'shortcuts.vdf'
        grid_dir = config_dir / 'grid'
        config_dir.mkdir(parents=True, exist_ok=True)

        icon_path, art_files = install_steam_artwork(
            grid_dir, appid_u32, game_dir=game_dir, fallback_icon=fallback_icon)
        all_artwork.extend(art_files)

        if vdf_path.is_file():
            shutil.copy2(vdf_path, vdf_path.with_suffix('.vdf.bak'))
            data = parse_vdf(vdf_path.read_bytes())
        else:
            data = {'shortcuts': {}}

        shortcuts = data.setdefault('shortcuts', {})
        existing_key = _matching_shortcut_key(shortcuts, app_name)
        if existing_key is None:
            next_idx = max((int(k) for k in shortcuts if str(k).isdigit()), default=-1) + 1
            entry_key = str(next_idx)
            last_play = 0
            tags = {'0': 'Port'}
        else:
            entry_key = existing_key
            existing = shortcuts[existing_key]
            last_play = int(existing.get('LastPlayTime', 0) or 0)
            existing_tags = existing.get('tags')
            tags = existing_tags if isinstance(existing_tags, dict) and existing_tags else {'0': 'Port'}

        shortcuts[entry_key] = {
            'appid': appid_u32,
            'AppName': app_name,
            'Exe': exe_q,
            'StartDir': start_q,
            'icon': str(icon_path) if icon_path else '',
            'ShortcutPath': '',
            'LaunchOptions': launch_options,
            'IsHidden': 0,
            'AllowDesktopConfig': 1,
            'AllowOverlay': 1,
            'OpenVR': 0,
            'Devkit': 0,
            'DevkitGameID': '',
            'DevkitOverrideAppID': 0,
            'LastPlayTime': last_play,
            'FlatpakAppID': '',
            'tags': tags,
        }

        tmp_path = vdf_path.with_suffix('.vdf.tmp')
        tmp_path.write_bytes(dump_vdf(data))
        os.replace(tmp_path, vdf_path)
        updated.append(vdf_path)

    return {'updated': updated, 'artwork': all_artwork, 'appid': appid_u32}
