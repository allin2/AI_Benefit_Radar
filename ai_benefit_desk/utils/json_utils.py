import json
from datetime import datetime, date
from typing import Any

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

def dumps_json(data: Any, indent: int = 2) -> str:
    """Serialize data to formatted JSON string."""
    return json.dumps(data, cls=CustomJSONEncoder, ensure_ascii=False, indent=indent)

def loads_json(json_str: str) -> Any:
    """Deserialize JSON string safely."""
    return json.loads(json_str)
