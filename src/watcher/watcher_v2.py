from pathlib import Path
import time
import shutil

WATCH_INTERVAL = 2  # seconds


class WatcherV2:
    def __init__(self, inbox: Path, case_id: str, handler):
        self.inbox = Path(inbox).expanduser()
        self.case_id = case_id
        self.handler = handler  # simple callback receiving file paths
        self.seen = set()

    def scan_once(self):
        if not self.inbox.exists():
            return []

        new_files = []
        for f in self.inbox.iterdir():
            if f.is_file() and not f.name.startswith(".") and f not in self.seen:
                self.seen.add(f)
                new_files.append(f)

        return new_files

    def start(self):
        while True:
            new_files = self.scan_once()
            for f in new_files:
                self.handler(f)
            time.sleep(WATCH_INTERVAL)