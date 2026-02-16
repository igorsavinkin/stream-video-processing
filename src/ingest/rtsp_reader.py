from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
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
        camera_name: Optional[str] = None,
        reconnect_delay: float = 2.0,
        fallback_mp4_path: Optional[str] = None,
    ) -> None:
        self.rtsp_url = rtsp_url
        self.target_fps = target_fps
        self.width = width
        self.height = height
        self.camera_name = camera_name
        self.reconnect_delay = reconnect_delay
        self.fallback_mp4_path = fallback_mp4_path
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_emit_time = 0.0
        self._using_fallback = False
        self._current_source = rtsp_url

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
        source = self._current_source
        if isinstance(source, str) and source.lower() in ("auto", "camera:auto"):
            return self._open_capture_auto(preferred_name=self.camera_name)
        if isinstance(source, str) and source.isdigit():
            source = int(source)
        if os.name == "nt":
            if isinstance(source, int):
                logger.info("camera_open source=%s backend=MSMF", source)
                cap = cv2.VideoCapture(source, cv2.CAP_MSMF)
                if not cap.isOpened():
                    logger.warning("camera_open_failed source=%s backend=MSMF", source)
                    cap.release()
                    logger.info("camera_open source=%s backend=DSHOW", source)
                    cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            elif isinstance(source, str) and source.startswith("video="):
                logger.info("camera_open source=%s backend=DSHOW", source)
                cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            else:
                logger.info("camera_open source=%s backend=default", source)
                cap = cv2.VideoCapture(source)
        else:
            logger.info("camera_open source=%s backend=default", source)
            cap = cv2.VideoCapture(source)
        if self.width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return cap
    
    def _try_fallback(self) -> bool:
        """Try to fallback to local MP4 if available and RTSP failed."""
        if self._using_fallback or not self.fallback_mp4_path:
            return False
        
        fallback_path = Path(self.fallback_mp4_path)
        if not fallback_path.exists():
            logger.warning("fallback_mp4_not_found path=%s", self.fallback_mp4_path)
            return False
        
        logger.info("fallback_to_mp4 rtsp_url=%s fallback=%s", self.rtsp_url, self.fallback_mp4_path)
        self._current_source = str(fallback_path.absolute())
        self._using_fallback = True
        return True

    def _open_capture_auto(self, preferred_name: Optional[str] = None) -> cv2.VideoCapture:
        max_index = 10
        backend = cv2.CAP_MSMF if os.name == "nt" else 0
        logger.info(
            "camera_auto_start backend=%s max_index=%s",
            "MSMF" if os.name == "nt" else "default",
            max_index,
        )
        camera_names = self._list_windows_cameras() if os.name == "nt" else []
        if camera_names:
            logger.info("camera_devices names=%s", camera_names)
        tried_indices: list[int] = []
        tried_names: list[str] = []
        if preferred_name and os.name == "nt":
            logger.info("camera_preferred name=%s", preferred_name)
            cap = cv2.VideoCapture(f"video={preferred_name}", cv2.CAP_DSHOW)
            tried_names.append(preferred_name)
            if self.width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            if self.height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            ok, frame = cap.read()
            if ok and frame is not None:
                logger.info("camera_found name=%s", preferred_name)
                return cap
            logger.warning("camera_preferred_failed name=%s", preferred_name)
            cap.release()
        available = []
        for idx in range(max_index):
            tried_indices.append(idx)
            cap = cv2.VideoCapture(idx, backend) if backend else cv2.VideoCapture(idx)
            if self.width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            if self.height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            ok, frame = cap.read()
            if ok and frame is not None:
                available.append(idx)
                logger.info("camera_found index=%s", idx)
                return cap
            cap.release()
            if os.name == "nt":
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if self.width:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                if self.height:
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                ok, frame = cap.read()
                if ok and frame is not None:
                    available.append(idx)
                    logger.info("camera_found index=%s backend=DSHOW", idx)
                    return cap
                cap.release()
        for name in camera_names:
            tried_names.append(name)
            cap = cv2.VideoCapture(f"video={name}", cv2.CAP_DSHOW)
            if self.width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            if self.height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            ok, frame = cap.read()
            if ok and frame is not None:
                logger.info("camera_found name=%s", name)
                return cap
            cap.release()
        logger.warning(
            "camera_auto_failed max_index=%s available=%s tried_indices=%s tried_names=%s",
            max_index,
            available,
            tried_indices,
            tried_names,
        )
        return cv2.VideoCapture(0, backend) if backend else cv2.VideoCapture(0)

    @staticmethod
    def _list_windows_cameras() -> list[str]:
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "$classes = @('Camera','Image');"
            "$names = @();"
            "foreach ($c in $classes) {"
            "try { $names += Get-PnpDevice -Class $c | Select-Object -ExpandProperty FriendlyName } catch {}"
            "};"
            "$names | Where-Object { $_ } | Sort-Object -Unique",
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return []
        if result.returncode != 0 or not result.stdout:
            return []
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return names

    def _run(self) -> None:
        cap = self._open_capture()
        consecutive_failures = 0
        max_failures_before_fallback = 3
        
        while not self._stop_event.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                consecutive_failures += 1
                logger.warning("RTSP read failed, consecutive_failures=%s", consecutive_failures)
                
                # Try fallback if we haven't already and have exceeded failure threshold
                if not self._using_fallback and consecutive_failures >= max_failures_before_fallback:
                    if self._try_fallback():
                        cap.release()
                        cap = self._open_capture()
                        consecutive_failures = 0
                        continue
                
                cap.release()
                time.sleep(self.reconnect_delay)
                cap = self._open_capture()
                continue
            
            # Reset failure counter on successful read
            consecutive_failures = 0
            now = time.time()
            if self.target_fps > 0:
                min_interval = 1.0 / self.target_fps
                if now - self._last_emit_time < min_interval:
                    continue
            with self._frame_lock:
                self._latest_frame = frame
            self._last_emit_time = now
        cap.release()
