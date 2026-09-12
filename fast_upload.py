from __future__ import annotations

import asyncio
import hashlib
import inspect
import math
import os
import time
from pathlib import Path
from typing import Callable

from telethon import helpers, utils
from telethon.network import MTProtoSender
from telethon.tl.functions.upload import SaveBigFilePartRequest, SaveFilePartRequest
from telethon.tl.types import InputFile, InputFileBig

ProgressCallback = Callable[[int, int], object]


class ProgressReporter:
    def __init__(self, label: str, interval: float = 0.4) -> None:
        self.label = label
        self.interval = interval
        self.started_at = time.monotonic()
        self.last_print_at = 0.0

    @staticmethod
    def _format_eta(seconds: float) -> str:
        if not math.isfinite(seconds) or seconds < 0:
            return "--:--"
        seconds = int(round(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def __call__(self, current: int, total: int) -> None:
        if total <= 0:
            return

        now = time.monotonic()
        if current < total and now - self.last_print_at < self.interval:
            return
        self.last_print_at = now

        elapsed = max(now - self.started_at, 0.001)
        speed = current / elapsed
        eta = (total - current) / speed if speed > 0 else float("inf")
        percent = min(100, int(current * 100 / total))
        current_mib = current / (1024 * 1024)
        total_mib = total / (1024 * 1024)
        speed_mib = speed / (1024 * 1024)

        print(
            f"\r{self.label}: {percent:3d}% "
            f"({current_mib:.1f}/{total_mib:.1f} MiB) "
            f"• {speed_mib:.2f} MiB/s • ETA {self._format_eta(eta)}",
            end="",
            flush=True,
        )


def validate_workers(value: int) -> int:
    workers = int(value)
    if workers < 1 or workers > 8:
        raise ValueError("--upload-workers deve ficar entre 1 e 8.")
    return workers


def upload_plan(file_size: int, workers: int) -> tuple[int, int, int]:
    if file_size <= 0:
        raise ValueError("Arquivo vazio não pode ser enviado.")

    part_size_kb = int(utils.get_appropriated_part_size(file_size))
    part_size = part_size_kb * 1024
    part_count = math.ceil(file_size / part_size)
    active_workers = min(validate_workers(workers), part_count)
    return part_size, part_count, active_workers


async def _notify(callback: ProgressCallback | None, current: int, total: int) -> None:
    if callback is None:
        return
    result = callback(current, total)
    if inspect.isawaitable(result):
        await result


async def _new_sender(client) -> MTProtoSender:
    dc = await client._get_dc(client.session.dc_id)
    sender = MTProtoSender(client.session.auth_key, loggers=client._log)
    await sender.connect(
        client._connection(
            dc.ip_address,
            dc.port,
            dc.id,
            loggers=client._log,
            proxy=client._proxy,
        )
    )
    return sender


async def upload_file_parallel(
    client,
    path: str | os.PathLike[str],
    *,
    workers: int = 4,
    progress_callback: ProgressCallback | None = None,
):
    file_path = Path(path)
    file_size = file_path.stat().st_size
    part_size, part_count, active_workers = upload_plan(file_size, workers)
    file_id = helpers.generate_random_long()
    is_large = file_size > 10 * 1024 * 1024
    md5 = None if is_large else hashlib.md5()

    senders: list[MTProtoSender] = []
    pending: list[asyncio.Task | None] = []
    pending_sizes: list[int] = []
    uploaded = 0

    async def finish_lane(index: int) -> None:
        nonlocal uploaded
        task = pending[index]
        if task is None:
            return
        await task
        uploaded += pending_sizes[index]
        pending[index] = None
        pending_sizes[index] = 0
        await _notify(progress_callback, uploaded, file_size)

    try:
        senders = list(await asyncio.gather(*(_new_sender(client) for _ in range(active_workers))))
        pending = [None] * active_workers
        pending_sizes = [0] * active_workers

        with file_path.open("rb") as stream:
            for part_index in range(part_count):
                lane = part_index % active_workers
                await finish_lane(lane)

                chunk = stream.read(part_size)
                if not chunk:
                    raise IOError("O arquivo terminou antes do tamanho esperado.")
                if md5 is not None:
                    md5.update(chunk)

                if is_large:
                    request = SaveBigFilePartRequest(file_id, part_index, part_count, chunk)
                else:
                    request = SaveFilePartRequest(file_id, part_index, chunk)

                pending_sizes[lane] = len(chunk)
                pending[lane] = asyncio.create_task(client._call(senders[lane], request))

        for lane in range(active_workers):
            await finish_lane(lane)

        if is_large:
            return InputFileBig(file_id, part_count, file_path.name)
        return InputFile(file_id, part_count, file_path.name, md5.hexdigest())
    finally:
        for task in pending:
            if task is not None and not task.done():
                task.cancel()
        if pending:
            await asyncio.gather(*(task for task in pending if task is not None), return_exceptions=True)
        if senders:
            await asyncio.gather(*(sender.disconnect() for sender in senders), return_exceptions=True)
