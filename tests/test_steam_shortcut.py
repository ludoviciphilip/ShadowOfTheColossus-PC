"""Steam non-Steam shortcut and artwork integration tests (launcher/sotc_steam.py)."""
import base64
from pathlib import Path
from paths import ROOT
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(ROOT / 'launcher'))
import sotc_steam  # noqa: E402

# Minimal valid 1x1 RGBA PNG so artwork tests work with or without Pillow installed.
_TINY_PNG = base64.b64decode(
    b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)


def _make_png(path: Path, size=(64, 64), color=(120, 90, 40, 255)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
        Image.new('RGBA', size, color).save(path, format='PNG')
    except ImportError:
        path.write_bytes(_TINY_PNG)


class SteamShortcutTests(unittest.TestCase):
    def test_vdf_round_trip_and_empty(self):
        self.assertEqual(sotc_steam.parse_vdf(b''), {'shortcuts': {}})

        sample = {
            'shortcuts': {
                '0': {
                    'appid': 0x81234567,
                    'AppName': 'Other Game',
                    'Exe': '"/usr/bin/other"',
                    'StartDir': '"/usr/bin"',
                    'icon': '',
                    'AllowOverlay': 1,
                    'tags': {'0': 'Favorite', '1': 'RPG'},
                }
            }
        }
        encoded = sotc_steam.dump_vdf(sample)
        decoded = sotc_steam.parse_vdf(encoded)
        self.assertEqual(decoded, sample)

    def test_steam_shortcut_appid_bit31_and_determinism(self):
        exe = '"/opt/SotC-PC-linux-x86_64.AppImage"'
        app_id = sotc_steam.steam_shortcut_appid(exe, 'Shadow of the Colossus')
        self.assertGreaterEqual(app_id, 0x80000000)
        self.assertLessEqual(app_id, 0xffffffff)
        self.assertEqual(app_id, sotc_steam.steam_shortcut_appid(exe, 'Shadow of the Colossus'))
        self.assertNotEqual(app_id, sotc_steam.steam_shortcut_appid(exe + 'x', 'Shadow of the Colossus'))

    def test_steam_launch_spec(self):
        exe, start_dir, opts = sotc_steam.steam_launch_spec(
            False, False, '/home/user/Games/SotC.AppImage', '/usr/bin/python3', Path('/src/sotc'))
        self.assertEqual(exe, '"/home/user/Games/SotC.AppImage"')
        self.assertEqual(start_dir, '"/home/user/Games"')
        self.assertEqual(opts, '--play')

        exe, start_dir, opts = sotc_steam.steam_launch_spec(
            False, False, '', '/usr/bin/python3', Path('/src/sotc'))
        self.assertEqual(exe, '"/usr/bin/python3"')
        self.assertEqual(start_dir, '"/src/sotc"')
        self.assertEqual(opts, '"/src/sotc/launcher/sotc_launcher_win.py" --play')

        exe, start_dir, opts = sotc_steam.steam_launch_spec(
            True, True, '', r'C:\Games\SotC\SotC.exe', Path(r'C:\Games\SotC'))
        self.assertIn('SotC.exe', exe)
        self.assertEqual(opts, '--play')

    def test_find_steam_userdata_dirs_dedups_symlinks_and_skips_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            real_userdata = home / '.local' / 'share' / 'Steam' / 'userdata'
            (real_userdata / '12345678').mkdir(parents=True)
            (real_userdata / '0').mkdir(parents=True)
            (real_userdata / 'anonymous').mkdir(parents=True)

            steam_link = home / '.steam' / 'steam'
            steam_link.parent.mkdir(parents=True)
            try:
                steam_link.symlink_to(home / '.local' / 'share' / 'Steam')
            except OSError:
                pass

            flatpak_userdata = (
                home / '.var' / 'app' / 'com.valvesoftware.Steam' / '.local' / 'share' / 'Steam' / 'userdata'
            )
            (flatpak_userdata / '87654321').mkdir(parents=True)

            found = sotc_steam.find_steam_userdata_dirs(home=home, is_windows=False)
            names = [p.name for p in found]
            self.assertEqual(names, ['12345678', '87654321'])

    def test_add_to_steam_preserves_existing_creates_backup_and_artwork(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_dir = root / 'userdata' / '999999'
            config_dir = user_dir / 'config'
            config_dir.mkdir(parents=True)
            vdf_path = config_dir / 'shortcuts.vdf'

            existing = {
                'shortcuts': {
                    '0': {
                        'appid': 0x80001234,
                        'AppName': 'Existing Game',
                        'Exe': '"/usr/bin/existing"',
                        'StartDir': '"/usr/bin"',
                        'LastPlayTime': 1700000000,
                        'tags': {'0': 'Action'},
                    }
                }
            }
            vdf_path.write_bytes(sotc_steam.dump_vdf(existing))

            game_dir = root / 'CUSA08809'
            _make_png(game_dir / 'sce_sys' / 'icon0.png', size=(512, 512))
            _make_png(game_dir / 'sce_sys' / 'pic1.png', size=(1920, 1080))

            res = sotc_steam.add_to_steam(
                '/opt/SotC-PC.AppImage', '/opt', '--play',
                game_dir=game_dir, userdata_dirs=[user_dir])

            self.assertEqual(res['updated'], [vdf_path])
            self.assertTrue((config_dir / 'shortcuts.vdf.bak').is_file())
            appid = res['appid']
            self.assertGreaterEqual(appid, 0x80000000)

            grid_dir = config_dir / 'grid'
            for suffix in ('_icon.png', '.png', 'p.png', '_hero.png'):
                self.assertTrue((grid_dir / f'{appid}{suffix}').is_file(), f'missing {suffix}')

            parsed = sotc_steam.parse_vdf(vdf_path.read_bytes())['shortcuts']
            self.assertIn('0', parsed)
            self.assertIn('1', parsed)
            self.assertEqual(parsed['0']['AppName'], 'Existing Game')
            self.assertEqual(parsed['1']['AppName'], 'Shadow of the Colossus')
            self.assertEqual(parsed['1']['Exe'], '"/opt/SotC-PC.AppImage"')
            self.assertEqual(parsed['1']['StartDir'], '"/opt"')
            self.assertEqual(parsed['1']['LaunchOptions'], '--play')
            self.assertEqual(parsed['1']['icon'], str(grid_dir / f'{appid}_icon.png'))

            # Updating in-place preserves LastPlayTime and does not duplicate entry '2'.
            parsed['1']['LastPlayTime'] = 1712345678
            vdf_path.write_bytes(sotc_steam.dump_vdf({'shortcuts': parsed}))

            sotc_steam.add_to_steam(
                '/opt/SotC-PC.AppImage', '/opt', '--play',
                game_dir=game_dir, userdata_dirs=[user_dir])
            parsed2 = sotc_steam.parse_vdf(vdf_path.read_bytes())['shortcuts']
            self.assertEqual(set(parsed2.keys()), {'0', '1'})
            self.assertEqual(parsed2['1']['LastPlayTime'], 1712345678)

    def test_add_to_steam_without_pillow_falls_back_to_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_dir = root / 'userdata' / '111111'
            fallback = root / 'sotc.png'
            fallback.write_bytes(_TINY_PNG)

            with mock.patch.dict(sys.modules, {'PIL': None, 'PIL.Image': None, 'PIL.ImageOps': None}):
                res = sotc_steam.add_to_steam(
                    '/opt/SotC.AppImage', '/opt', '--play',
                    fallback_icon=fallback, userdata_dirs=[user_dir])

            appid = res['appid']
            grid_dir = user_dir / 'config' / 'grid'
            self.assertEqual((grid_dir / f'{appid}_icon.png').read_bytes(), _TINY_PNG)
            self.assertEqual((grid_dir / f'{appid}p.png').read_bytes(), _TINY_PNG)

    def test_add_to_steam_no_userdata_dirs_graceful(self):
        res = sotc_steam.add_to_steam('/opt/SotC.AppImage', '/opt', userdata_dirs=[])
        self.assertEqual(res, {'updated': [], 'artwork': [], 'appid': 0})


if __name__ == '__main__':
    unittest.main()
