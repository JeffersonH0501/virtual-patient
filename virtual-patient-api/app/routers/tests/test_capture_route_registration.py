"""The deployed application exposes the capture API used by the browser."""


def test_application_registers_segment_capture_routes():
    from main import app

    paths = app.openapi()["paths"]
    for suffix in ("/segments", "/resume", "/segments/finalize",
                   "/segments/{segment_id}/seal", "/segments/{segment_id}/media"):
        assert "post" in paths[f"/medical-interviews/{{interview_id}}/recording{suffix}"]
