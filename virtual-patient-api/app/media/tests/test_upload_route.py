import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request
from starlette.formparsers import SpooledTemporaryFile
from starlette.requests import ClientDisconnect

from app.media.upload_route import RecordingMultipartParser


@pytest.mark.parametrize("disconnect", [True, False])
def test_partial_multipart_spool_closes_on_disconnect_or_limit(disconnect):
    messages = iter([
        {
            "type": "http.request",
            "body": b'--x\r\nContent-Disposition: form-data; name="video"; filename="clip.webm"\r\n\r\n1234',
            "more_body": True,
        },
        {"type": "http.disconnect"} if disconnect else {
            "type": "http.request", "body": b"5678\r\n--x--\r\n", "more_body": False,
        },
    ])

    async def receive():
        return next(messages)

    request = Request({"type": "http", "headers": [(b"content-type", b"multipart/form-data; boundary=x")]}, receive)
    spool = SpooledTemporaryFile(max_size=1)
    with patch("starlette.formparsers.SpooledTemporaryFile", return_value=spool):
        with pytest.raises(ClientDisconnect if disconnect else HTTPException) as raised:
            asyncio.run(RecordingMultipartParser(request, {"video": 5}, 1000).parse())
    if not disconnect:
        assert raised.value.status_code == 413
    assert spool.closed
