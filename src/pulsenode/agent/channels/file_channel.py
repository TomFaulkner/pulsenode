"""File-based channel for debugging and simulation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path

from structlog import get_logger

logger = get_logger(__name__)


@dataclass
class FileChannelMcp:
    file_path: Path
    name: str = "FileChannel"
    type: str = "file"
    identifier: str = ""
    sleep_seconds: float = 3.0
    thread_id: str | None = None  # For threaded channels (email threads, etc.)

    _batch_index: int = field(default=0, init=False, repr=False)
    _message_index: int = field(default=0, init=False, repr=False)
    _batches: list[list[str]] = field(default_factory=list, init=False, repr=False)
    _last_mtime: float = field(default=0, init=False, repr=False)

    def _parse_file(self) -> list[list[str]]:
        """Parse the file into batches of messages."""
        if not self.file_path.exists():
            return []

        content = self.file_path.read_text()
        batches: list[list[str]] = []
        current_batch: list[str] = []

        for line in content.splitlines():
            line = line.strip()

            if line == "+++":
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
            elif line == "---":
                continue  # Skip separator lines
            elif line:
                current_batch.append(line)

        # Don't forget the last batch
        if current_batch:
            batches.append(current_batch)

        return batches

    def _reload_if_needed(self) -> bool:
        """Reload file if modified. Returns True if file was reloaded."""
        if not self.file_path.exists():
            return False

        current_mtime = self.file_path.stat().st_mtime
        if current_mtime > self._last_mtime:
            logger.info("file_channel_reloaded", path=str(self.file_path))
            self._last_mtime = current_mtime
            self._batch_index = 0
            self._message_index = 0
            self._batches = self._parse_file()
            return True

        return False

    async def receive_messages(self) -> AsyncGenerator[str]:
        """Yield messages from the file.

        Yields messages one at a time within a batch.
        When batch is exhausted, yields empty string to signal "no more messages".
        Next poll continues with next batch (after +++).
        When file is exhausted, yields empty string forever.
        """
        while True:
            # Reload file if modified
            self._reload_if_needed()

            # If no batches, yield empty string forever (like real channel)
            if not self._batches:
                yield ""
                await asyncio.sleep(self.sleep_seconds)
                continue

            # Check if we've consumed all batches
            if self._batch_index >= len(self._batches):
                yield ""
                await asyncio.sleep(self.sleep_seconds)
                continue

            # Get current batch
            batch = self._batches[self._batch_index]

            # Check if we've consumed all messages in current batch
            if self._message_index >= len(batch):
                # Batch exhausted - yield empty string to signal end of batch
                self._batch_index += 1
                self._message_index = 0
                yield ""
                continue

            # Yield next message from current batch
            message = batch[self._message_index]
            self._message_index += 1

            logger.debug(
                "file_channel_message",
                channel=self.name,
                batch=self._batch_index,
                message=self._message_index,
            )

            await asyncio.sleep(self.sleep_seconds)
            yield message
