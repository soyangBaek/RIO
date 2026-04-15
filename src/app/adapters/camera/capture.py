from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from src.app.adapters.camera.storage import PhotoStorage


_DUMMY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxAQEBUQEBIVFRUVFRUVFRUVFRUVFRUVFRUWFhUVFRUYHSggGBolHRUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGxAQGy0lICYtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMBIgACEQEDEQH/xAAbAAABBQEBAAAAAAAAAAAAAAADAAIEBQYBB//EADYQAAEDAgQDBgQEBwAAAAAAAAECAwQFEQASIQYxQVEHEyJhcYGRMqGx8BRCUrHB0eHxFiMzQ1P/xAAZAQADAQEBAAAAAAAAAAAAAAABAgMABAX/xAAjEQACAgICAgICAwAAAAAAAAAAAQIRAyESMQQTQVEiMmFx/9oADAMBAAIRAxEAPwDO1REQEREBERAREQEREBERAUVVJbq7h9OStfMWrEyA0sqKoYfY3ZweS0xZ3V6dYgW9v3fV6NNa4yV0vUhD5r9lqg9qiOVyPkQfR2j2o7Jf/2Q=="
)


@dataclass(slots=True)
class WebcamCapture:
    storage: PhotoStorage

    def capture(self, *, trace_id: str | None = None) -> str:
        del trace_id
        target = self.storage.next_photo_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_DUMMY_JPEG)
        return str(target)
