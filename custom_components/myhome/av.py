"""Helpers for MyHOME WHO=7 multimedia and video door entry commands."""

from __future__ import annotations

from OWNd.message import OWNAVCommand

ATTR_DIAL_COL = "dial_col"
ATTR_DIAL_ROW = "dial_row"
ATTR_OPERATION = "operation"
ATTR_WHERE = "where"

SERVICE_VIDEO_COMMAND = "video_command"

VIDEO_OPERATION_TO_FRAME = {
    "close_video": "*7*9**##",
    "zoom_in": "*7*120##",
    "zoom_out": "*7*121##",
    "x_up": "*7*130##",
    "x_down": "*7*131##",
    "y_up": "*7*140##",
    "y_down": "*7*141##",
    "brightness_up": "*7*150##",
    "brightness_down": "*7*151##",
    "contrast_up": "*7*160##",
    "contrast_down": "*7*161##",
    "color_up": "*7*170##",
    "color_down": "*7*171##",
    "quality_up": "*7*180##",
    "quality_down": "*7*181##",
}


def _normalize_camera_where(where: int | str | None) -> int:
    if where is None:
        raise ValueError("Missing camera WHERE.")
    where = int(where)
    if 0 <= where <= 99:
        return 4000 + where
    if 4000 <= where <= 4999:
        return where
    raise ValueError("Invalid camera WHERE.")


def _normalize_dial_value(value: int | str | None) -> int:
    value = int(value)
    if value < 1 or value > 4:
        raise ValueError("Dial coordinates must be between 1 and 4.")
    return value


def build_video_command(
    operation: str,
    *,
    where: int | str | None = None,
    dial_row: int | str | None = None,
    dial_col: int | str | None = None,
) -> str:
    """Build a WHO=7 command."""
    operation = str(operation)

    if operation == "receive_video":
        command = OWNAVCommand.receive_video(str(_normalize_camera_where(where)))
        if command is None:
            raise ValueError("Invalid camera WHERE.")
        return str(command)

    if operation == "dial":
        row = _normalize_dial_value(dial_row)
        col = _normalize_dial_value(dial_col)
        return f"*7*3{row}{col}##"

    if operation not in VIDEO_OPERATION_TO_FRAME:
        raise ValueError(f"Unsupported video operation `{operation}`.")

    return VIDEO_OPERATION_TO_FRAME[operation]
