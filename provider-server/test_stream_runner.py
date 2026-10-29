"""Offline tests for provider stream process lifecycle and safe failures."""

import importlib.util
import io
import os
from pathlib import Path
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("main.py")
SPEC = importlib.util.spec_from_file_location("nexora_provider_test", MODULE_PATH)
provider = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provider)
REAL_GET_FFMPEG_BINARY = provider.get_ffmpeg_binary


class FakeResponse:
    status_code = 200

    def __init__(self, body=None):
        self.body = body or {"action": "continue"}

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class FakeProcess:
    def __init__(self, stdout_lines=(), stderr_lines=(), exit_code=None):
        self.stdout = iter(stdout_lines)
        self.stderr = iter(stderr_lines)
        self.exit_code = exit_code
        self.terminated = False

    def poll(self):
        return self.exit_code if self.exit_code is not None else (-15 if self.terminated else None)

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return self.poll()

    def kill(self):
        self.terminated = True


def stream_data():
    return {
        "session_id": "stream_test123",
        "provider_id": "provider_test",
        "source_url": "rtsp://media.invalid/live/stream_test123?key=private-read-key",
        "destination_url": "rtmp://destination.invalid/live",
        "destination_key": "private-destination-key",
        "profile_name": "720p30",
        "encoding_config": {
            "width": 1280, "height": 720, "fps": 30,
            "video_bitrate_kbps": 3000, "audio_bitrate_kbps": 160,
            "video_encoder": "libx264",
        },
    }


class StreamRunnerTests(unittest.TestCase):
    def setUp(self):
        provider.STREAM_ENCODERS = ["libx264"]
        provider.get_ffmpeg_binary = lambda: "ffmpeg-test"
        provider.active_streams.clear()
        provider.BASE = provider.DEFAULT_LOCAL_URL
        provider.ALLOW_LOCAL_BACKEND_FAILOVER = True

    def run_with_process(self, process, stop_event=None, request_handler=None, retry_attempt=0):
        calls = []
        process_queue = list(process) if isinstance(process, (list, tuple)) else None
        launches = []

        def make_process(*args, **kwargs):
            launches.append(args[0])
            return process_queue.pop(0) if process_queue is not None else process

        def fake_request(method, path, **kwargs):
            calls.append((method, path, kwargs.get("json", {})))
            if request_handler:
                return request_handler(kwargs.get("json", {}))
            return FakeResponse()

        with patch.object(provider.subprocess, "Popen", side_effect=make_process), \
             patch.object(provider, "request", side_effect=fake_request):
            provider.run_stream_encoder(stream_data(), stop_event or provider.threading.Event(), retry_attempt)
        return calls, launches

    def test_absent_input_times_out_without_fake_metrics_or_secret_logging(self):
        proc = FakeProcess()
        with patch.dict(os.environ, {"STREAM_INPUT_TIMEOUT_SECONDS": "1"}):
            calls, _ = self.run_with_process(proc)
        stopped = [body for method, path, body in calls if path.endswith("/stopped")][-1]
        self.assertEqual(stopped["status"], "FAILED")
        self.assertIn("No media input arrived", stopped["error"])
        self.assertEqual(stopped["metrics"], {"status": "WAITING_FOR_INPUT"})
        self.assertTrue(proc.terminated)

    def test_destination_failure_is_sanitized(self):
        proc = FakeProcess(stderr_lines=[
            "Input #0: RTSP media input",
            "Stream #0:0: Video: h264, 30 fps",
            "[flv] Connection refused while writing output",
        ], exit_code=1)
        calls, _ = self.run_with_process(proc, retry_attempt=2)
        stopped = [body for method, path, body in calls if path.endswith("/stopped")][-1]
        self.assertEqual(stopped["status"], "FAILED")
        self.assertIn("could not reach the destination", stopped["error"])
        self.assertNotIn("destination.invalid", stopped["error"])
        self.assertNotIn("private-destination-key", stopped["error"])

    def test_destination_write_error_is_reported_without_sensitive_details(self):
        message = provider._stream_error_message(
            ["av_interleaved_write_frame(): Broken pipe to rtmp://destination.invalid/live/private-destination-key"],
            True,
        )
        self.assertIn("could not publish encoded output", message)
        self.assertNotIn("destination.invalid", message)
        self.assertNotIn("private-destination-key", message)

    def test_browser_vp8_input_is_transcoded_to_youtube_h264_aac_flv(self):
        # MediaMTX's RTSP reader may expose VP8/Opus from Browser Capture;
        # output is explicitly encoded into the H.264/AAC FLV profile used by RTMP.
        data = stream_data()
        args = provider._build_stream_ffmpeg_args("ffmpeg-test", data, data["encoding_config"], "libx264")
        self.assertEqual(args[args.index("-rtsp_transport") + 1], "tcp")
        self.assertEqual(args[args.index("-c:v") + 1], "libx264")
        self.assertEqual(args[args.index("-c:a") + 1], "aac")
        self.assertEqual(args[args.index("-f") + 1], "flv")
        self.assertEqual(args[-1], "rtmp://destination.invalid/live/private-destination-key")
        self.assertNotIn("copy", args)

    def test_youtube_publish_rejection_is_clear_and_does_not_disclose_key(self):
        message = provider._stream_error_message(
            ["Input #0: RTSP", "[rtmp] Server error: NetStream.Publish.BadName"], True,
        )
        self.assertIn("destination rejected", message)
        self.assertNotIn("private-destination-key", message)

    def test_verified_progress_reports_streaming_and_stop_is_session_scoped(self):
        proc = FakeProcess(stdout_lines=[
            "frame=1", "fps=30.0", "bitrate=1000.0kbits/s", "speed=1.0x", "progress=continue",
        ], stderr_lines=["Input #0: RTSP media input", "Stream #0:0: Video: h264, 30 fps"])
        stop_event = provider.threading.Event()

        def stop_after_streaming(body):
            if body.get("status") == "STREAMING":
                stop_event.set()
            return FakeResponse()

        calls, _ = self.run_with_process(proc, stop_event, stop_after_streaming)
        states = [body.get("status") for _, path, body in calls if path.endswith("/heartbeat")]
        self.assertIn("ENCODING", states)
        self.assertIn("STREAMING", states)
        stopped = [body for method, path, body in calls if path.endswith("/stopped")][-1]
        self.assertEqual(stopped["status"], "STOPPED")
        self.assertEqual(stopped["metrics"].get("fps"), 30.0)
        self.assertEqual(stopped["metrics"].get("bitrate_kbps"), 1000.0)
        self.assertEqual(stopped["metrics"].get("speed"), "1.0x")
        self.assertTrue(proc.terminated)

    def test_transient_media_disconnect_retries_the_same_session(self):
        failed_attempt = FakeProcess(stderr_lines=[
            "Input #0: RTSP media input",
            "[rtsp] Connection timed out",
        ], exit_code=1)
        recovered_attempt = FakeProcess(stdout_lines=[
            "frame=1", "fps=30.0", "bitrate=950.0kbits/s", "speed=1.0x", "progress=continue",
        ], stderr_lines=["Input #0: RTSP media input"])
        stop_event = provider.threading.Event()

        def stop_after_streaming(body):
            if body.get("status") == "STREAMING":
                stop_event.set()
            return FakeResponse()

        calls, launches = self.run_with_process(
            [failed_attempt, recovered_attempt], stop_event, stop_after_streaming,
        )
        self.assertEqual(len(launches), 2)
        stopped = [body for method, path, body in calls if path.endswith("/stopped")][-1]
        self.assertEqual(stopped["status"], "STOPPED")
        self.assertIn("STREAMING", [body.get("status") for _, path, body in calls if path.endswith("/heartbeat")])

    def test_missing_rtsp_publisher_keeps_session_alive_until_input_deadline(self):
        # MediaMTX returns 404 for a path before OBS or Browser Capture starts
        # publishing. FFmpeg exits immediately; that must not finalize the
        # session and revoke the WHIP credential before the browser can connect.
        absent_source = lambda: FakeProcess(
            stderr_lines=["[rtsp] method DESCRIBE failed: 404 Not Found"],
            exit_code=1,
        )
        stop_event = provider.threading.Event()
        with patch.dict(os.environ, {"STREAM_INPUT_TIMEOUT_SECONDS": "1"}):
            calls, launches = self.run_with_process(
                [absent_source(), absent_source()],
                stop_event,
                retry_attempt=0,
            )
        stopped = [body for method, path, body in calls if path.endswith("/stopped")]
        states = [body.get("status") for _, path, body in calls if path.endswith("/heartbeat")]
        self.assertEqual(len(launches), 2)
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0]["status"], "FAILED")
        self.assertIn("No media input arrived", stopped[0]["error"])
        self.assertIn("WAITING_FOR_INPUT", states)

    def test_authentication_error_is_human_readable_and_safe(self):
        message = provider._stream_error_message(["401 Unauthorized key=do-not-log"], False)
        self.assertIn("could not authenticate", message)
        self.assertNotIn("do-not-log", message)

    def test_ingest_network_error_is_not_misreported_as_destination_failure(self):
        message = provider._stream_error_message(["RTSP connection timed out"], False)
        self.assertIn("could not read media from Nexora ingest", message)

    def test_explicit_ffmpeg_path_is_used_when_configured(self):
        with patch.object(provider, "get_ffmpeg_binary", REAL_GET_FFMPEG_BINARY), \
             patch.dict(os.environ, {"NEXORA_FFMPEG_PATH": str(MODULE_PATH)}), \
             patch.object(provider.shutil, "which") as which:
            self.assertEqual(provider.get_ffmpeg_binary(), str(MODULE_PATH.resolve()))
        which.assert_not_called()

    def test_invalid_explicit_ffmpeg_path_does_not_silently_select_another_binary(self):
        with patch.object(provider, "get_ffmpeg_binary", REAL_GET_FFMPEG_BINARY), \
             patch.dict(os.environ, {"NEXORA_FFMPEG_PATH": "X:/missing/ffmpeg.exe"}), \
             patch.object(provider.shutil, "which", return_value=None):
            self.assertIsNone(provider.get_ffmpeg_binary())

    def test_provider_registration_auth_failure_never_fails_over_or_retries(self):
        error = provider.requests.HTTPError("unauthorized")
        error.response = type("Response", (), {"status_code": 401})()
        output = io.StringIO()
        with patch.object(provider, "request", side_effect=error), redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "same value on this provider and backend"):
                provider.register(retry_indefinitely=True)
        self.assertEqual(provider.BASE, provider.DEFAULT_LOCAL_URL)
        self.assertNotIn("local-demo-token", output.getvalue())


if __name__ == "__main__":
    unittest.main()
