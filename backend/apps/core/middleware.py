import re
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .logging import REQUEST_ID_HEADER, new_request_id, reset_request_id, set_request_id

# Accept a caller-supplied ID only if it looks like one; never echo arbitrary header input.
_VALID_ID = re.compile(r"^[A-Za-z0-9_.-]{8,64}$")


class RequestIDMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        rid = incoming if _VALID_ID.match(incoming) else new_request_id()
        token = set_request_id(rid)
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)
        response[REQUEST_ID_HEADER] = rid
        return response
