"""HTTP boundary shared by RPC handlers; no duplicated banking rules."""
import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class UpstreamError(Exception):
    def __init__(self, status, body):
        super().__init__(body.get("message", "REST request failed"))
        self.status, self.body = status, body


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward authentication to a redirected host.


class RestClient:
    def __init__(self, base_url):
        url = urlsplit(base_url)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise ValueError("REST_BASE_URL must be an HTTP(S) URL without credentials")
        if url.query or url.fragment:
            raise ValueError("REST_BASE_URL cannot contain query or fragment")
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method, path, body=None, authorization=None, timeout=5):
        headers = {"Accept": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data, headers, method=method)
        try:
            with self.opener.open(req, timeout=max(0.001, timeout)) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                payload = json.load(error)
                if not isinstance(payload, dict):
                    raise ValueError("non-object error")
            except (ValueError, UnicodeError):
                payload = {"code": "UPSTREAM_ERROR", "message": "REST returned a non-JSON error"}
            finally:
                error.close()
            raise UpstreamError(error.code, payload) from error
        except (TimeoutError, socket.timeout) as error:
            raise UpstreamError(504, {"code": "UPSTREAM_TIMEOUT", "message": "REST request timed out"}) from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise UpstreamError(504, {"code": "UPSTREAM_TIMEOUT", "message": "REST request timed out"}) from error
            raise UpstreamError(503, {"code": "SERVICE_UNAVAILABLE", "message": "REST service unavailable"}) from error
        except OSError as error:
            raise UpstreamError(503, {"code": "SERVICE_UNAVAILABLE", "message": "REST service unavailable"}) from error
        except (ValueError, UnicodeError) as error:
            raise UpstreamError(502, {"code": "INVALID_UPSTREAM_RESPONSE", "message": "REST returned invalid JSON"}) from error
