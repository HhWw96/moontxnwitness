"""Exercise the public action's download, input and exit-code boundaries."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
from zipfile import ZipFile


ENTRY = Path(__file__).resolve().parents[1] / ".github/actions/check-point-window/check.py"
SPEC = importlib.util.spec_from_file_location("point_window_action", ENTRY)
ACTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACTION)


class Response(io.BytesIO):
    status = 200
    url = "https://release-assets.githubusercontent.com/portable"


class ActionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mtw-action-test-")
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        paths = {}
        for name in ("CAPSULE", "CONFIG", "POLICY"):
            path = self.directory / (name + " with spaces.json")
            path.write_text("{}", encoding="utf-8")
            paths["MTW_" + name] = str(path)
        self.inputs = {
            "RUNNER_TEMP": str(self.directory),
            "MTW_RELEASE_VERSION": "0.6.4",
            "MTW_PORTABLE_SHA256": "a" * 64,
            **paths,
        }

    def test_input_rejection_requires_no_network(self):
        for variable, bad in [
            ("MTW_RELEASE_VERSION", "v0.6.4"),
            ("MTW_RELEASE_VERSION", "../0.6.4"),
            ("MTW_PORTABLE_SHA256", "abcdef"),
            ("MTW_MAX_POINT_CHECKS", "1000001"),
            ("MTW_CAPSULE", "missing.json"),
        ]:
            with self.subTest(variable=variable, value=bad), patch.object(ACTION, "urlopen") as open_url:
                with self.assertRaises(ValueError):
                    ACTION.run_check({**self.inputs, variable: bad})
                open_url.assert_not_called()

    def test_matching_download_is_pinned_to_the_public_version(self):
        content = b"actual bytes returned by the release endpoint"
        digest = hashlib.sha256(content).hexdigest()
        archive = self.directory / "asset.zip"
        with patch.object(ACTION, "urlopen", return_value=Response(content)) as open_url:
            ACTION.download_portable("0.6.4", digest, archive)
        self.assertEqual(archive.read_bytes(), content)
        self.assertEqual(
            open_url.call_args.args[0].full_url,
            "https://github.com/HhWw96/moontxnwitness/releases/download/v0.6.4/MoonTxnWitness-v0.6.4-portable.zip",
        )

    def test_digest_mismatch_and_network_failure_do_not_extract_or_run(self):
        for value in (Response(b"wrong bytes"), URLError("offline")):
            with self.subTest(response=type(value).__name__), patch.object(
                ACTION, "urlopen"
            ) as open_url, patch.object(ACTION, "unpack_runtime") as unpack, patch.object(
                ACTION.subprocess, "run"
            ) as run:
                if isinstance(value, URLError):
                    open_url.side_effect = value
                else:
                    open_url.return_value = value
                with patch.dict(ACTION.os.environ, self.inputs, clear=True):
                    self.assertEqual(ACTION.main(), 2)
                unpack.assert_not_called()
                run.assert_not_called()

    def test_zip_rejects_traversal_and_case_collisions_before_extracting(self):
        root = "MoonTxnWitness-v0.6.4"
        for names in (
            [f"{root}/dist/../other"],
            [f"{root}/dist/manifest.json", f"{root}/dist/Manifest.json"],
        ):
            with self.subTest(names=names):
                archive = self.directory / "candidate.zip"
                target = self.directory / "output"
                with ZipFile(archive, "w") as zipped:
                    zipped.writestr(f"{root}/{ACTION.GATE}", "")
                    for name in names:
                        zipped.writestr(name, "")
                with self.assertRaises(ValueError):
                    ACTION.unpack_runtime(archive, target, "0.6.4")
                self.assertFalse(target.exists())

    def test_exit_codes_and_paths_are_preserved(self):
        for code in (0, 1, 2):
            verdict = {
                "accepted": code == 0,
                "verifiedRefutation": code == 1,
                "sourceCoverageComplete": code != 2,
            }
            output_path = self.directory / f"outputs-{code}"
            with self.subTest(code=code), patch.object(ACTION, "download_portable"), patch.object(
                ACTION, "unpack_runtime", return_value=self.directory / "gate.mjs"
            ), patch.object(
                ACTION.subprocess, "run",
                return_value=subprocess.CompletedProcess([], code, json.dumps(verdict)),
            ) as run, patch.dict(ACTION.os.environ, {**self.inputs, "GITHUB_OUTPUT": str(output_path)}, clear=True):
                self.assertEqual(ACTION.main(), code)
                self.assertIn(str(Path(self.inputs["MTW_CAPSULE"]).resolve()), run.call_args.args[0])
                output = dict(row.split("=", 1) for row in output_path.read_text(encoding="utf-8").splitlines())
                self.assertEqual(output, {
                    "exit-code": str(code),
                    "verdict": json.dumps(verdict, separators=(",", ":")),
                })

    def test_inconsistent_success_is_a_failure(self):
        with patch.object(ACTION, "download_portable"), patch.object(
            ACTION, "unpack_runtime", return_value=self.directory / "gate.mjs"
        ), patch.object(ACTION.subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 0, '{"accepted":false,"verifiedRefutation":false,"sourceCoverageComplete":true}'
        )), patch.dict(ACTION.os.environ, self.inputs, clear=True):
            self.assertEqual(ACTION.main(), 2)


if __name__ == "__main__":
    unittest.main()
