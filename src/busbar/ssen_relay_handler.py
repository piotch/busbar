"""Standalone standard-library Lambda handler for the SSEN catalogue."""
import base64
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 4 * 1024 * 1024  # Base64 and metadata must fit Invoke's 6 MB limit.
SOURCE = "https://data-api.ssen.co.uk/catalog.rdf"


def validate_url(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.netloc != "data-api.ssen.co.uk"
            or parts.path != "/catalog.rdf" or parts.fragment):
        raise ValueError("Only the HTTPS SSEN catalogue endpoint is allowed")
    query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True)
    if parts.query and (set(query) != {"page"} or len(query["page"]) != 1
                        or not query["page"][0].isascii()
                        or not query["page"][0].isdigit()
                        or int(query["page"][0]) < 1):
        raise ValueError("Only a positive page query parameter is allowed")


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def lambda_handler(event, context):
    url = event.get("url", SOURCE)
    validate_url(url)
    request = Request(url, headers={
        "Accept": "application/rdf+xml",
        "User-Agent": "Busbar-catalogue-observer/0.1",
    })
    try:
        response = build_opener(SafeRedirect()).open(request, timeout=60)
    except HTTPError as exc:
        response = exc
    with response:
        content = response.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValueError("SSEN relay response exceeds 4 MiB")
        return {
            "schema_version": 1,
            "status": response.code,
            "final_url": response.url,
            "headers": {name: response.headers.get(name) for name in
                        ("Content-Type", "ETag", "Last-Modified")},
            "body_base64": base64.b64encode(content).decode("ascii"),
        }
