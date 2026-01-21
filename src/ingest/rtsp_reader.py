from __future__ import annotations

import logging
import os
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
        if isinstance(source, str) and source.lower() in ("auto", "camera:auto"):
            return self._open_capture_auto()
        if isinstance(source, str) and source.isdigit():
            source = int(source)
        if os.name == "nt" and (
            isinstance(source, int)
            or (isinstance(source, str) and source.startswith("video="))
        ):
            cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(source)
        if self.width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return cap

    def _open_capture_auto(self) -> cv2.VideoCapture:
        max_index = 10
        backend = cv2.CAP_DSHOW if os.name == "nt" else 0
        for idx in range(max_index):
            cap = cv2.VideoCapture(idx, backend) if backend else cv2.VideoCapture(idx)
            if self.width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            if self.height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            ok, frame = cap.read()
            if ok and frame is not None:
                logger.info("camera_found index=%s", idx)
                return cap
            cap.release()
        logger.warning("camera_auto_failed max_index=%s", max_index)
        return cv2.VideoCapture(0, backend) if backend else cv2.VideoCapture(0)

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
