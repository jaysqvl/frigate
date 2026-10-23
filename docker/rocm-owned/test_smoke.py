"""Check service shutdown evidence without Docker or vendor runtimes."""

import unittest

from smoke import validate_shutdown

CLEAN_EXIT = "[INFO] Service Frigate exited with code 0 (by signal 0)\n"
STOPPED = "s6-rc: info: service frigate successfully stopped\n"


class ServiceShutdown(unittest.TestCase):
    def test_accepts_clean_service_with_normal_container_status(self):
        for code in (0, 143):
            with self.subTest(code=code):
                result = validate_shutdown(
                    {"Status": "exited", "OOMKilled": False, "ExitCode": code},
                    CLEAN_EXIT + STOPPED,
                )
                self.assertEqual(result["graceful_service_shutdown"], "passed")
                self.assertEqual(result["frigate_exit_code"], 0)
                self.assertEqual(result["container_exit_code"], code)

    def test_rejects_crashes_forced_kills_and_unfinished_containers(self):
        for change in (
            {"ExitCode": 1},
            {"ExitCode": 137},
            {"ExitCode": 139},
            {"Status": "running"},
            {"OOMKilled": True},
        ):
            with self.subTest(change=change), self.assertRaises(AssertionError):
                validate_shutdown(
                    {"Status": "exited", "OOMKilled": False, "ExitCode": 143} | change,
                    CLEAN_EXIT + STOPPED,
                )

    def test_requires_final_service_exit_and_subsequent_stop_marker(self):
        failed_exit = "Service Frigate exited with code 1 (by signal 0)\n"
        signal_exit = "Service Frigate exited with code 0 (by signal 15)\n"
        for log in (
            "",
            STOPPED,
            CLEAN_EXIT,
            STOPPED + CLEAN_EXIT,
            failed_exit + STOPPED,
            signal_exit + STOPPED,
            CLEAN_EXIT + STOPPED + failed_exit + STOPPED,
            CLEAN_EXIT + STOPPED + CLEAN_EXIT,
        ):
            with self.subTest(log=log), self.assertRaises(AssertionError):
                validate_shutdown(
                    {"Status": "exited", "OOMKilled": False, "ExitCode": 143}, log
                )


if __name__ == "__main__":
    unittest.main()
