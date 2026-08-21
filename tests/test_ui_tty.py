import hashlib
import os
import select
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path


def read_pty_until(fd: int, marker: bytes, timeout: float = 5.0) -> bytes:
    output = bytearray()
    deadline = time.monotonic() + timeout
    while marker not in output:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"Timed out waiting for {marker!r}")
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            continue
        try:
            chunk = os.read(fd, 16_384)
        except OSError:
            break
        if not chunk:
            break
        output.extend(chunk)
    if marker not in output:
        raise AssertionError(f"PTY closed before {marker!r} was received")
    return bytes(output)


@unittest.skipUnless(os.name == "posix", "PTY test requires a POSIX terminal")
class TTYInputTests(unittest.TestCase):
    def test_multiline_input_accepts_a_single_line_beyond_max_canon(self):
        payload = "x" * 6_520
        expected_digest = hashlib.sha256(payload.encode()).hexdigest()
        project_root = Path(__file__).resolve().parents[1]
        script = (
            "import hashlib\n"
            "from ui import UI\n"
            "value = UI().prompt_multiline('Paste text') or ''\n"
            "encoded = value.encode()\n"
            "print(f'RESULT:{len(encoded)}:{hashlib.sha256(encoded).hexdigest()}', flush=True)\n"
        )
        master_fd, slave_fd = os.openpty()
        process = subprocess.Popen(
            [sys.executable, "-c", script],
            cwd=project_root,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)
        writer = None
        write_errors = []

        try:
            read_pty_until(master_fd, b"Use ':menu' for the main menu")
            data = f"{payload}\nEOF\n".encode()

            def write_input() -> None:
                try:
                    remaining = data
                    while remaining:
                        remaining = remaining[os.write(master_fd, remaining):]
                except OSError as error:
                    write_errors.append(error)

            writer = threading.Thread(target=write_input, daemon=True)
            writer.start()
            expected_result = f"RESULT:6520:{expected_digest}".encode()
            output = read_pty_until(master_fd, expected_result)
            writer.join(timeout=5)
            self.assertFalse(writer.is_alive())
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            os.close(master_fd)
            if writer is not None:
                writer.join(timeout=1)

        self.assertEqual(process.returncode, 0)
        self.assertFalse(writer.is_alive())
        self.assertEqual(write_errors, [])
        self.assertIn(expected_result, output)

    def test_ui_disables_automatic_readline_history(self):
        project_root = Path(__file__).resolve().parents[1]
        script = (
            "import readline\n"
            "import ui\n"
            "input('API key: ')\n"
            "print(f'HISTORY:{readline.get_current_history_length()}', flush=True)\n"
        )
        master_fd, slave_fd = os.openpty()
        process = subprocess.Popen(
            [sys.executable, "-c", script],
            cwd=project_root,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)

        try:
            read_pty_until(master_fd, b"API key: ")
            os.write(master_fd, b"sk-test-secret\n")
            output = read_pty_until(master_fd, b"HISTORY:0")
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            os.close(master_fd)

        self.assertEqual(process.returncode, 0)
        self.assertIn(b"HISTORY:0", output)


if __name__ == "__main__":
    unittest.main()
