from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np


logger = logging.getLogger(__name__)


class RTSPFrameReader:
    def __init__(
        self,
        rtsp_url: str,
        target_fps: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
        reconnect_delay: float = 2.0,
    ) -> None:
        self.rtsp_url = rtsp_url
        self.target_fps = target_fps
        self.width = width
        self.height = height
        self.reconnect_delay = reconnect_delay
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_emit_time = 0.0

    def start(self) -> "RTSPFrameReader":
        if self._thread and self._thread.is_alive():
            return self
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def read(self) -> Optional[np.ndarray]:
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def _open_capture(self) -> cv2.VideoCapture:
        source = self.rtsp_url
        if isinstance(source, str) and source.isdigit():
            source = int(source)
        cap = cv2.VideoCapture(source)
        if self.width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return cap

    def _run(self) -> None:
        cap = self._open_capture()
        while not self._stop_event.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                logger.warning("RTSP read failed, reconnecting...")
                cap.release()
                time.sleep(self.reconnect_delay)
                cap = self._open_capture()
                continue
            now = time.time()
            if self.target_fps > 0:
                min_interval = 1.0 / self.target_fps
                if now - self._last_emit_time < min_interval:
                    continue
            with self._frame_lock:
                self._latest_frame = frame
            self._last_emit_time = now
        cap.release()
