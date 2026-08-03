from typing import Any


def ok(data: Any = None, message: str = "Thành công") -> dict:
    return {"success": True, "message": message, "data": data if data is not None else {}}
