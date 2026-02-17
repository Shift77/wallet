import logging
import json

logger = logging.getLogger(__name__)


class RequestResponseLoggingMiddleware:
    """
    Middleware that logs each request method, path, body,
    and the corresponding response content.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # We need to read the body before passing it to the view,
        # but standard request.body access is cached by Django.

        request_body = ""
        content_type = request.META.get("CONTENT_TYPE", "")

        # Skip logging body for file uploads
        if "multipart/form-data" in content_type:
            request_body = "<Multipart form data - body not logged>"
        else:
            try:
                # Log request body for POST/PUT/PATCH
                if request.method in ["POST", "PUT", "PATCH"]:
                    if request.body:
                        # Try to decode as utf-8, fallback if binary
                        request_body = request.body.decode("utf-8")
            except Exception:
                request_body = "<Could not decode body>"

        logger.info(
            f"API Request: {request.method} {request.get_full_path()} Body: {request_body}"
        )

        response = self.get_response(request)

        # Log response content
        response_content = ""
        response_type = response.get("Content-Type", "")

        try:
            # Only log small text/json content to avoid massive logs for files
            if (
                response_type.startswith("application/json")
                or response_type.startswith("text/")
                or response_type.startswith("application/xml")
            ):

                if hasattr(response, "content"):
                    response_content = response.content.decode("utf-8")
                elif hasattr(response, "streaming_content"):
                    # Do not consume streaming content
                    response_content = "<Streaming content>"
            else:
                response_content = f"<Content-Type: {response_type}>"

        except Exception:
            response_content = "<Could not decode content>"

        logger.info(
            f"API Response: {request.method} {request.get_full_path()} "
            f"Status: {response.status_code} Content: {response_content}"
        )

        return response
