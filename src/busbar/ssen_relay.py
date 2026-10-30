"""Optional authenticated London Lambda transport; direct fetches need no AWS SDK."""
import base64
from io import BytesIO
import json
import os
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit

from .ssen_relay_handler import MAX_BYTES, validate_url


def relay_for(url):
    function = os.environ.get("BUSBAR_SSEN_RELAY_FUNCTION", "").strip()
    if not function or urlsplit(url).hostname != "data-api.ssen.co.uk":
        return None
    if not re.fullmatch(r"arn:aws:lambda:eu-west-2:[0-9]{12}:function:[A-Za-z0-9_-]+", function):
        raise ValueError("BUSBAR_SSEN_RELAY_FUNCTION must be an unqualified London Lambda ARN")
    validate_url(url)
    return function


class RelayResponse(BytesIO):
    def __init__(self, content, result):
        super().__init__(content)
        self.status = result["status"]
        self.url = result["final_url"]
        self.headers = result["headers"]


def fetch(url, function):
    import boto3
    from botocore.config import Config

    client = boto3.client("lambda", region_name="eu-west-2", config=Config(
        connect_timeout=15, read_timeout=90, retries={"max_attempts": 2},
    ))
    result = client.invoke(
        FunctionName=function, InvocationType="RequestResponse",
        Payload=json.dumps({"url": url}).encode(),
    )
    stream = result["Payload"]
    try:
        raw = stream.read(6 * 1024 * 1024 + 1)
    finally:
        stream.close()
    if result.get("FunctionError"):
        raise RuntimeError("SSEN relay Lambda execution failed")
    if result.get("StatusCode") != 200 or len(raw) > 6 * 1024 * 1024:
        raise ValueError("Invalid SSEN relay invocation response")
    data = json.loads(raw)
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported SSEN relay response")
    validate_url(data["final_url"])
    content = base64.b64decode(data["body_base64"], validate=True)
    if len(content) > MAX_BYTES:
        raise ValueError("SSEN relay response exceeds 4 MiB")
    if not isinstance(data["status"], int) or not 200 <= data["status"] <= 599:
        raise ValueError("Invalid SSEN HTTP status")
    if not 200 <= data["status"] < 300:
        raise HTTPError(url, data["status"], "SSEN relay upstream HTTP failure",
                        data["headers"], None)
    return RelayResponse(content, data)
