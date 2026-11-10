"""Limit recording multipart uploads before Starlette spools them to disk."""

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from python_multipart.multipart import parse_options_header
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect

from app.media.storage import MIB, RECORDING_FILE_LIMITS, TURN_VIDEO_MAX_BYTES, check_upload_size


class RecordingMultipartParser(MultiPartParser):
    def __init__(self, request: Request, limits: dict[str, int], request_limit: int):
        super().__init__(request.headers, self.bounded_stream(request, request_limit),
                         max_files=len(limits), max_fields=8)
        self.limits = limits
        self.seen_files: set[str] = set()
        self.file_bytes = 0

    @staticmethod
    async def bounded_stream(request: Request, limit: int):
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            check_upload_size(received, limit)
            yield chunk

    def on_headers_finished(self) -> None:
        super().on_headers_finished()
        part = self._current_part
        if part.file is not None:
            if part.field_name not in self.limits or part.field_name in self.seen_files:
                raise MultiPartException("Unexpected or duplicate recording media field")
            self.seen_files.add(part.field_name)
            self.file_bytes = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self.file_bytes += end - start
            check_upload_size(self.file_bytes, self.limits[self._current_part.field_name])
        super().on_part_data(data, start, end)

    async def parse(self):
        try:
            return await super().parse()
        except BaseException:
            # Starlette only closes partial uploads for multipart and OS errors.
            for file in self._files_to_close_on_error:
                file.close()
            raise


class RecordingUploadRoute(APIRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()
        if self.path.endswith("/recording/finalize") or self.path.endswith("/segments/{segment_id}/media"):
            limits = RECORDING_FILE_LIMITS
        elif self.path.endswith("/chunks/{kind}/{index}"):
            limits = {"file": TURN_VIDEO_MAX_BYTES}
        elif self.path.endswith("/recording/blocks/{block_id}"):
            limits = {"file": RECORDING_FILE_LIMITS["student_video"]}
        elif self.path.endswith("/recording/turns/{turn_id}/video"):
            limits = {"video": TURN_VIDEO_MAX_BYTES}
        else:
            return handle

        async def handle_upload(request: Request):
            content_type, _ = parse_options_header(request.headers.get("content-type"))
            is_multipart = content_type == b"multipart/form-data"
            request_limit = sum(limits.values()) + 4 * MIB if is_multipart else MIB
            declared = request.headers.get("content-length")
            if declared and declared.isascii() and declared.isdecimal() and len(declared) <= 20:
                check_upload_size(int(declared), request_limit)
            if is_multipart:
                try:
                    # Reuse this form for FastAPI's existing field validation and file cleanup.
                    request._form = await RecordingMultipartParser(request, limits, request_limit).parse()
                except MultiPartException as error:
                    raise HTTPException(status_code=400, detail=error.message) from error
                except ClientDisconnect as error:
                    raise HTTPException(status_code=400, detail="Recording upload disconnected") from error
            elif content_type == b"application/x-www-form-urlencoded":
                receive = request.receive
                received = 0

                async def bounded_receive():
                    nonlocal received
                    message = await receive()
                    received += len(message.get("body", b""))
                    check_upload_size(received, request_limit)
                    return message

                request = Request(request.scope, bounded_receive)
            return await handle(request)

        return handle_upload
