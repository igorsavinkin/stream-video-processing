from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    rtsp_url: str = Field(
        default="rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mov"
    )
    frame_sample_fps: int = 2
    frame_width: int = 640
    frame_height: int = 360
    model_name: str = "mobilenet_v3_small"
    device: str = "cpu"
    metrics_log_every: int = 50
    save_processed: bool = False
    processed_dir: str = "data/processed"
    class_topk: int = 5
    person_score_threshold: float = 0.6
    camera_name: Optional[str] = None
    config_path: Optional[str] = None

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        extra="ignore",
        protected_namespaces=(),
    )


class YamlSettings(BaseModel):
    rtsp_url: Optional[str] = None
    frame_sample_fps: Optional[int] = None
    frame_width: Optional[int] = None
    frame_height: Optional[int] = None
    model_name: Optional[str] = None
    device: Optional[str] = None
    metrics_log_every: Optional[int] = None
    save_processed: Optional[bool] = None
    processed_dir: Optional[str] = None
    class_topk: Optional[int] = None
    person_score_threshold: Optional[float] = None
    camera_name: Optional[str] = None

    model_config = {
        "protected_namespaces": (),
    }


def load_settings() -> Settings:
    settings = Settings()
    config_path = settings.config_path or os.getenv("APP_CONFIG_PATH")
    if not config_path:
        return settings

    path = Path(config_path)
    if not path.exists():
        return settings

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    yaml_settings = YamlSettings(**payload)
    merged = settings.model_copy(update=yaml_settings.model_dump(exclude_none=True))
    return merged


settings = load_settings()
