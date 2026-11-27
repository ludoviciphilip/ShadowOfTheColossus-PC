"""Linux launcher behavior: SDL3 display parsing, refresh rate, monitor selection, and native texts."""
from paths import ROOT
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(ROOT / 'launcher'))
try:
    import sotc_launcher_win as launcher  # noqa: E402
except ImportError as error:  # no Tkinter
    launcher = None
    REASON = str(error)


@unittest.skipIf(launcher is None, 'launcher not importable')
class LinuxDisplayTests(unittest.TestCase):
    def test_parse_single_and_fractional_refresh_rates(self):
        for raw_hz, expected_hz in (('59.95', 60), ('143.98', 144), ('90.00', 90), ('0.00', 0)):
            text = f'DISPLAY\t1\t1\t0\t0\t1920\t1080\t{raw_hz}\tDP-1\n'
            parsed = launcher._parse_linux_displays(text)
            self.assertEqual(len(parsed), 1)
            device_id, label, centre, primary, hz = parsed[0]
            self.assertEqual((device_id, centre, primary, hz), ('DP-1', (960, 540), True, expected_hz))
            self.assertIn('1920 × 1080', label)
            if expected_hz:
                self.assertIn(f'({expected_hz} Hz)', label)
            else:
                self.assertNotIn('Hz', label)

    def test_parse_multi_monitor_primary_first_and_negative_offsets(self):
        text = '\n'.join([
            'DISPLAY\t2\t0\t-1920\t-120\t1920\t1080\t60.00\tHDMI-A-1',
            'DISPLAY\t1\t1\t0\t0\t2560\t1440\t143.98\tDP-1',
        ])
        parsed = launcher._parse_linux_displays(text)
        self.assertEqual([d[0] for d in parsed], ['DP-1', 'HDMI-A-1'])
        self.assertEqual(parsed[0][2:], ((1280, 720), True, 144))
        self.assertEqual(parsed[1][2:], ((-960, 420), False, 60))

    def test_parse_duplicate_names_disambiguated(self):
        text = '\n'.join([
            'DISPLAY\t1\t1\t0\t0\t1920\t1080\t60.00\tDP-1',
            'DISPLAY\t2\t0\t1920\t0\t2560\t1440\t120.00\tDP-1',
            'DISPLAY\t3\t0\t4480\t0\t1280\t800\t90.00\t',
        ])
        parsed = launcher._parse_linux_displays(text)
        self.assertEqual([d[0] for d in parsed], ['DP-1', 'DP-1 #2', 'Monitor 3'])

    def test_parse_ignores_malformed_and_zero_dimension_lines(self):
        text = '\n'.join([
            'not a display line',
            'DISPLAY\t1\t1\t0\t0',
            'DISPLAY\t2\t1\tbad\t0\t1920\t1080\t60.00\tDP-1',
            'DISPLAY\t3\t0\t0\t0\t0\t1080\t60.00\tDP-2',
            'DISPLAY\t4\t0\t0\t0\t1920\t0\t60.00\tDP-3',
            'DISPLAY\t5\t1\t0\t0\t1280\t800\t90.00\teDP-1',
        ])
        parsed = launcher._parse_linux_displays(text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0][0], 'eDP-1')

    def test_monitors_and_screen_refresh_hz(self):
        sample = [
            ('DP-1', 'DP-1 — 2560 × 1440 (144 Hz) (principal)', (1280, 720), True, 144),
            ('HDMI-A-1', 'HDMI-A-1 — 1920 × 1080 (120 Hz)', (3520, 540), False, 120),
            ('DP-2', 'DP-2 — 1280 × 720', (640, 1800), False, 0),
        ]
        with mock.patch.object(launcher, 'IS_WINDOWS', False), \
             mock.patch.object(launcher, '_LINUX_DISPLAYS', sample):
            mons = launcher.monitors()
            self.assertEqual(len(mons), 3)
            self.assertEqual(mons[0], ('DP-1', 'DP-1 — 2560 × 1440 (144 Hz) (principal)', (1280, 720), True))
            self.assertEqual(launcher.screen_refresh_hz(), 144)
            self.assertEqual(launcher.screen_refresh_hz('HDMI-A-1'), 120)
            self.assertEqual(launcher.screen_refresh_hz('DP-2'), 60)
            self.assertEqual(launcher.screen_refresh_hz('missing'), 144)

        with mock.patch.object(launcher, 'IS_WINDOWS', False), \
             mock.patch.object(launcher, '_LINUX_DISPLAYS', []):
            self.assertEqual(launcher.monitors(), [])
            self.assertEqual(launcher.screen_refresh_hz(), 60)

    def test_game_environment_dynamic_fps_and_monitor_at(self):
        for hz, expected_step in ((144, '48'), (90, '45'), (120, '40')):
            sample = [
                ('DP-1', f'DP-1 — 2560 × 1440 ({hz} Hz)', (1280, 720), True, hz),
                ('HDMI-A-1', 'HDMI-A-1 — 1920 × 1080 (120 Hz)', (3520, 540), False, 120),
            ]
            with self.subTest(hz=hz), \
                 mock.patch.object(launcher, 'IS_WINDOWS', False), \
                 mock.patch.object(launcher, '_LINUX_DISPLAYS', sample):
                env = launcher.game_environment({**launcher.APP_DEFAULTS, 'fps_mode': '60', 'fps_dynamic': True})
                self.assertEqual(env['SOTC_FPS_DYNAMIC'], expected_step)
                self.assertNotIn('SOTC_MONITOR_AT', env)

                env_sec = launcher.game_environment({
                    **launcher.APP_DEFAULTS,
                    'fps_mode': '60',
                    'fps_dynamic': True,
                    'game_monitor': 'HDMI-A-1',
                })
                self.assertEqual(env_sec['SOTC_FPS_DYNAMIC'], '40')
                self.assertEqual(env_sec['SOTC_MONITOR_AT'], '3520,540')

    @unittest.skipIf(launcher is None or launcher.IS_WINDOWS, 'Linux-only UI label check')
    def test_linux_audio_channel_label_avoids_windows(self):
        pt, en = launcher.AUDIO_CHANNELS[0][1]
        self.assertNotIn('Windows', pt)
        self.assertNotIn('Windows', en)


if __name__ == '__main__':
    unittest.main()
