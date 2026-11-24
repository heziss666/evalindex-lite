import hashlib
import json
import os
from contextlib import contextmanager
from threading import Lock


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@contextmanager
def run_lock(output):
    with (output / ".lock").open("a+b") as stream:
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("Another command is using this run directory") from exc
        yield


class Journal:
    def __init__(self, path, read_only=False):
        self.path = path
        self.rows = {}
        self.lock = Lock()
        if path.exists():
            with path.open("rb" if read_only else "r+b") as stream:
                start = 0
                for line in stream:
                    if not line.endswith(b"\n"):
                        if not read_only:
                            stream.seek(start)
                            stream.truncate()
                        break
                    row = json.loads(line)
                    self.rows[row["key"]] = row
                    start += len(line)

    def get(self, key):
        with self.lock:
            return self.rows.get(key)

    def append(self, row):
        line = json.dumps(row, ensure_ascii=False).encode("utf-8") + b"\n"
        with self.lock:
            with self.path.open("ab") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
            self.rows[row["key"]] = row


def write_report(path, value, *, jsonl=False):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        if jsonl:
            for row in value:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    temporary.replace(path)
