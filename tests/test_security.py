"""Deterministic alarm transitions and real file processing boundaries."""

import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import unittest

import shlex
import yaml

import jinja2

ROOT = Path(__file__).resolve().parents[1]
ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(ROOT / 'config/custom_templates'))
MACROS = ENV.get_template('seguridad.jinja').module


def transition(previous=None, command='presence', occupancy='on', now=1000, cutoff=10000, **kwargs):
    return json.loads(MACROS.transition(previous or {}, command, occupancy, now, cutoff, **kwargs))


class AlarmRules(unittest.TestCase):
    def test_night_arrivals_and_morning(self):
        night = transition(command='arm_night')['context']
        self.assertEqual(transition(night)['context']['mode'], 'armed_night')
        self.assertEqual(transition(night, now=10000, command='morning')['context']['mode'], 'disarmed')
        away = transition(night, occupancy='off')['context']
        self.assertEqual(away['mode'], 'armed_away')
        self.assertEqual(transition(away, occupancy='off', now=10000, command='morning')['context']['mode'], 'armed_away')

    def test_all_pause_durations_and_restart(self):
        for minutes in [30, 60, 120, 180]:
            with self.subTest(minutes=minutes):
                night = transition(command='arm_night', cutoff=30000)['context']
                paused = transition(night, command='pause', minutes=minutes)['context']
                deadline = 1000 + 60 * minutes
                self.assertEqual(paused['paused_until'], deadline)
                recovered = transition(paused, command='recover', now=deadline - 1, occupancy='off')['context']
                self.assertEqual(recovered['mode'], 'disarmed')
                self.assertEqual(recovered['paused_until'], deadline)
                self.assertEqual(transition(paused, command='recover', now=deadline)['context']['mode'], 'armed_night')
                self.assertEqual(transition(paused, command='resume', now=deadline, occupancy='off')['context']['mode'], 'armed_away')

    def test_pause_across_cutoff_does_not_restore_night(self):
        night = transition(command='arm_night', cutoff=2000)['context']
        paused = transition(night, command='pause', minutes=30)['context']
        self.assertEqual(transition(paused, command='morning', now=2000)['context']['mode'], 'disarmed')
        self.assertEqual(transition(paused, command='resume', now=2800)['context']['mode'], 'disarmed')
        self.assertEqual(transition(paused, command='resume', now=2800, occupancy='off')['context']['mode'], 'armed_away')

    def test_manual_commands_cancel_pause(self):
        paused = transition(transition(command='arm_night')['context'], command='pause', minutes=30)['context']
        manual = transition(paused, command='disarm')['context']
        self.assertEqual(manual['paused_until'], 0)
        self.assertTrue(manual['manual_hold'])
        self.assertEqual(transition(manual, command='recover', now=30000, occupancy='off')['context']['mode'], 'disarmed')
        armed = transition(paused, command='arm_away')['context']
        self.assertEqual(armed['paused_until'], 0)
        self.assertFalse(armed['manual_hold'])

    def test_repeated_pause_keeps_original_night_and_replaces_deadline(self):
        paused = transition(transition(command='arm_night')['context'], command='pause', minutes=30)['context']
        extended = transition(paused, command='pause', minutes=60, now=1100)['context']
        self.assertEqual(extended['paused_mode'], 'armed_night')
        self.assertEqual(extended['night_cutoff'], paused['night_cutoff'])
        self.assertEqual(extended['paused_until'], 4700)

    def test_exclusions_survive_trigger_recovery_but_not_next_arm(self):
        night = transition(command='arm_night')['context']
        excluded = transition(night, command='exclude', detector='binary_sensor.door')['context']
        self.assertEqual(transition(excluded, command='recover')['context']['excluded'], ['binary_sensor.door'])
        self.assertEqual(transition(excluded, command='arm_night')['context']['excluded'], [])
        self.assertEqual(transition(excluded, occupancy='off')['context']['excluded'], [])

    def test_unknown_presence_does_not_mean_empty(self):
        night = transition(command='arm_night')['context']
        away = transition(command='arm_away')['context']
        for mode in [night, away]:
            self.assertEqual(transition(mode, occupancy='unavailable')['context']['mode'], mode['mode'])
        paused = transition(night, command='pause', minutes=30)['context']
        self.assertEqual(transition(paused, occupancy='unavailable', now=4000)['context']['mode'], 'disarmed')

    def test_camera_resolution_is_unambiguous_and_confined(self):
        cameras = {'a': {'ftp_directories': ['/media/camera/a/']}}
        resolve = lambda path: json.loads(MACROS.camera_for_path(cameras, path))
        self.assertEqual(resolve('/media/camera/a/date/clip.mkv'), 'a')
        for path in ['/media/camera/ab/clip.mkv', '/media/camera/a/../b/clip.mkv', '/tmp/a/clip.mkv']:
            self.assertEqual(resolve(path), '')
        cameras['b'] = {'ftp_directories': ['/media/camera/a/date/']}
        self.assertEqual(resolve('/media/camera/a/date/clip.mkv'), '')

    def test_registered_camera_paths_and_source_formats(self):
        cameras = yaml.safe_load((ROOT / 'config/seguridad/camaras.yaml').read_text(encoding='utf-8'))
        expected = {
            'entrada': ('/media/camera/puerta_principal', 'mp4'),
            'cocina': ('/media/camera/C1_00626E8305E1', 'mkv'),
            'recibidor': ('/media/camera/C1_00626E615161', 'mkv'),
            'piscina': ('/media/camera/FI9853EP_00626E563E69', 'mkv'),
            'barbacoa': ('/media/camera/FI9900P_00626E6D21B2', 'mkv'),
            'salon': ('/media/camera/FoscamCamera_00626ED836A9', 'mkv'),
            'caseta': ('/media/aqara_video/lumi3.99aa9fe51953f04f', 'mp4'),
        }
        for name, (folder, extension) in expected.items():
            with self.subTest(camera=name):
                self.assertEqual(json.loads(MACROS.camera_for_path(cameras, f'{folder}/date/clip.{extension}')), name)
                wrong = 'mp4' if extension == 'mkv' else 'mkv'
                self.assertEqual(json.loads(MACROS.camera_for_path(cameras, f'{folder}/date/clip.{wrong}')), '')


class MediaFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        package = yaml.load((ROOT / 'config/packages/system.yaml').read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
        self.command = jinja2.Environment().from_string(package['shell_command']['mp4_convert'])

    def arguments(self, source):
        return shlex.split(self.command.render(file=str(source)))

    def test_conversion_quotes_paths_and_replaces_only_final_extension(self):
        source = self.root / 'directory.mkv' / "clip with spaces;$(echo test)'s.MKV"
        args = self.arguments(source)
        self.assertEqual(args[args.index('-i') + 1], str(source))
        self.assertEqual(args[-1], str(source.with_suffix('.mp4')))
        self.assertEqual(args[args.index('-c') + 1], 'copy')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg is required')
    def test_real_mkv_is_remuxed_to_playable_mp4(self):
        source = self.root / "clip with spaces;$(echo test)'s.mkv"
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'color=c=black:s=32x32:d=0.2', '-c:v', 'libx264', str(source)], check=True)
        subprocess.run(self.arguments(source), check=True)
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=format_name',
                                '-of', 'json', str(source.with_suffix('.mp4'))],
                               check=True, capture_output=True, text=True)
        self.assertIn('mp4', json.loads(probe.stdout)['format']['format_name'])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg is required')
    def test_bad_video_returns_failure(self):
        source = self.root / 'broken.mkv'
        source.write_bytes(b'not a video')
        result = subprocess.run(self.arguments(source), capture_output=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
