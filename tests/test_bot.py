"""Offline tests for bot.py. No phone, Telegram network or camera needed:
termux commands are stubbed, the telegram package is replaced by a stub,
and the web API is exercised through Flask's test client."""
import asyncio
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

# --- Stub the telegram packages before importing bot.py ---
tg = types.ModuleType("telegram")
tg.Update = object
tge = types.ModuleType("telegram.ext")


class _FakeBotApp:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)


class _Builder:
    def token(self, _t):
        return self

    def build(self):
        return _FakeBotApp()


class _Application:
    @staticmethod
    def builder():
        return _Builder()


tge.Application = _Application
tge.CommandHandler = lambda cmd, fn: (cmd, fn)
tge.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
sys.modules["telegram"] = tg
sys.modules["telegram.ext"] = tge

# --- Config in a temp HOME before import ---
_tmp = tempfile.mkdtemp()
os.environ["HOME"] = _tmp
with open(os.path.join(_tmp, ".cctv_config.json"), "w") as f:
    json.dump({"token": "x", "allowed_users": [42], "web_password": "s3cret",
               "stream_port": 8554, "web_port": 5000}, f)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
bot = importlib.import_module("bot")


class FakeProc:
    """Stands in for the ffmpeg subprocess."""

    def __init__(self, *a, **k):
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15


def fake_update(user_id):
    return types.SimpleNamespace(
        effective_user=None if user_id is None else types.SimpleNamespace(id=user_id)
    )


class WebAuthTests(unittest.TestCase):
    def setUp(self):
        self.client = bot.app.test_client()

    def test_dashboard_requires_auth(self):
        self.assertEqual(self.client.get("/").status_code, 401)

    def test_wrong_password_rejected(self):
        self.assertEqual(self.client.get("/", auth=("u", "wrong")).status_code, 401)

    def test_correct_password_accepted(self):
        self.assertEqual(self.client.get("/", auth=("u", "s3cret")).status_code, 200)

    def test_empty_password_never_matches(self):
        self.assertFalse(bot.check_auth(""))
        self.assertFalse(bot.check_auth(None))


class SensorParsingTests(unittest.TestCase):
    DICT_PAYLOAD = {"Proximity sensor": {"values": [5.0, 0.0]}}

    def test_status_reads_proximity_from_real_termux_shape(self):
        def fake_cmd(args, capture=False, timeout=10):
            if "termux-battery-status" in args:
                return '{"percentage": 87}'
            if "termux-sensor" in args:
                return json.dumps(self.DICT_PAYLOAD)
            return ""
        with mock.patch.object(bot, "cmd", side_effect=fake_cmd):
            r = bot.app.test_client().get("/status", auth=("u", "s3cret"))
        data = r.get_json()
        self.assertEqual(data["battery"], 87)
        self.assertEqual(data["proximity"], 5.0,
                         "termux-sensor returns an object keyed by sensor name, not a list")

    def test_sensor_values_accepts_both_shapes(self):
        self.assertEqual(bot.sensor_values(self.DICT_PAYLOAD, "Proximity sensor"), [5.0, 0.0])
        self.assertEqual(bot.sensor_values([{"values": [1.0]}], "Proximity sensor"), [1.0])
        self.assertIsNone(bot.sensor_values({"Other": {"values": [1]}} , "Proximity sensor"))

    def test_format_sensors_renders_dict_shape(self):
        text = bot.format_sensors({"Accelerometer": {"values": [0.1, 9.8, 0.0]},
                                   "Proximity sensor": {"values": [5.0]}})
        self.assertIn("Accelerometer: 0.1, 9.8, 0.0", text)
        self.assertIn("Proximity sensor: 5.0", text)


class StreamLivenessTests(unittest.TestCase):
    def setUp(self):
        bot.STREAM_PROC = None
        self.client = bot.app.test_client()

    def _status_stream(self):
        return self.client.get("/status", auth=("u", "s3cret")).get_json()["stream"]

    def test_stream_reports_real_liveness(self):
        with mock.patch.object(bot.subprocess, "Popen", FakeProc):
            self.assertFalse(self._status_stream())
            self.assertTrue(bot.start_stream())
            self.assertTrue(self._status_stream())
            self.assertFalse(bot.start_stream(), "second start while running must refuse")
            # ffmpeg crashes: the status must flip to off without any toggle
            bot.STREAM_PROC.returncode = 1
            self.assertFalse(self._status_stream(),
                             "a dead ffmpeg must not keep reporting as running")
            self.assertTrue(bot.start_stream(), "restart after a crash must work")
            self.assertTrue(bot.stop_stream())
            self.assertTrue(bot.STREAM_PROC is None)

    def test_stop_stream_terminates_only_a_live_process(self):
        with mock.patch.object(bot.subprocess, "Popen", FakeProc) as _:
            bot.start_stream()
            proc = bot.STREAM_PROC
            self.assertTrue(bot.stop_stream())
            self.assertTrue(proc.terminated)

    def test_web_stream_toggle(self):
        with mock.patch.object(bot.subprocess, "Popen", FakeProc):
            r = self.client.post("/stream", auth=("u", "s3cret"))
            self.assertTrue(r.get_json()["stream"])
            r = self.client.post("/stream", auth=("u", "s3cret"))
            self.assertFalse(r.get_json()["stream"])

    def tearDown(self):
        bot.STREAM_PROC = None


class TelegramAuthTests(unittest.TestCase):
    def test_allowed_user_passes(self):
        self.assertTrue(asyncio.run(bot.auth(fake_update(42))))

    def test_stranger_rejected(self):
        self.assertFalse(asyncio.run(bot.auth(fake_update(7))))

    def test_channel_post_without_user_does_not_crash(self):
        self.assertFalse(asyncio.run(bot.auth(fake_update(None))),
                         "channel posts have effective_user=None and must not crash the handler")


class TorchTests(unittest.TestCase):
    def test_torch_toggles(self):
        bot.TORCH_ON = False
        with mock.patch.object(bot, "cmd", return_value=True):
            r1 = bot.app.test_client().post("/torch", auth=("u", "s3cret"))
            r2 = bot.app.test_client().post("/torch", auth=("u", "s3cret"))
        self.assertTrue(r1.get_json()["torch"])
        self.assertFalse(r2.get_json()["torch"])


if __name__ == "__main__":
    unittest.main()
