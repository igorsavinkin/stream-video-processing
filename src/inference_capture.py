from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import cv2
from PIL import Image

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except Exception:  # pragma: no cover - optional dependency
    boto3 = None
    BotoCoreError = ClientError = Exception

logger = logging.getLogger("capture")


@dataclass
class InferenceCapture:
    enabled: bool
    output_dir: Path
    every_n: int = 1
    s3_bucket: Optional[str] = None
    s3_prefix: str = "inference"
    _counter: int = 0
    _s3_client: Any = field(default=None, init=False)

    def maybe_capture(
        self,
        *,
        image_bgr: Optional[Any] = None,
        image_pil: Optional[Image.Image] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        if not self.enabled:
            return
        self._counter += 1
        if self.every_n > 1 and (self._counter % self.every_n) != 0:
            return

        try:
            ts = time.time()
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            day_dir = self.output_dir / dt.strftime("%Y/%m/%d")
            day_dir.mkdir(parents=True, exist_ok=True)

            base = f"{dt.strftime('%H%M%S')}_{uuid4().hex}"
            image_path = day_dir / f"{base}.jpg"
            meta_path = day_dir / f"{base}.json"

            if image_pil is not None:
                image_pil.save(image_path, format="JPEG")
            elif image_bgr is not None:
                cv2.imwrite(str(image_path), image_bgr)
            else:
                return

            payload = metadata or {}
            payload.update(
                {
                    "timestamp": dt.isoformat(),
                    "image": image_path.name,
                }
            )
            meta_path.write_text(json.dumps(payload), encoding="utf-8")

            if self.s3_bucket:
                self._upload_file(
                    image_path,
                    f"{self.s3_prefix}/{dt.strftime('%Y/%m/%d')}/{image_path.name}",
                )
                self._upload_file(
                    meta_path,
                    f"{self.s3_prefix}/{dt.strftime('%Y/%m/%d')}/{meta_path.name}",
                )
        except Exception as exc:  # pragma: no cover - observability path
            logger.warning("capture_failed error=%s", exc)

    def _upload_file(self, path: Path, key: str) -> None:
        if boto3 is None:
            logger.warning("capture_s3_disabled reason=boto3_missing")
            return
        if self._s3_client is None:
            self._s3_client = boto3.client("s3")
        try:
            self._s3_client.upload_file(str(path), self.s3_bucket, key)
        except (BotoCoreError, ClientError) as exc:
            logger.warning("capture_s3_upload_failed key=%s error=%s", key, exc)
