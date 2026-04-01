"""
Duplicate requests: same request_id must return identical response and not reprocess.
"""


def test_duplicate_request_returns_same_status(client, loan_request):
    resp1 = client.post("/workflow/submit", json=loan_request)
    resp2 = client.post("/workflow/submit", json=loan_request)

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["status"] == resp2.json()["status"]
    assert resp1.json()["decision"] == resp2.json()["decision"]


def test_duplicate_request_has_replay_header(client, loan_request):
    client.post("/workflow/submit", json=loan_request)
    resp2 = client.post("/workflow/submit", json=loan_request)
    assert resp2.headers.get("X-Idempotent-Replay") == "true"


def test_duplicate_does_not_double_process(client, loan_request):
    """Audit trail length should not grow on replay."""
    resp1 = client.post("/workflow/submit", json=loan_request)
    resp2 = client.post("/workflow/submit", json=loan_request)

    trail1 = len(resp1.json()["audit_trail"])
    trail2 = len(resp2.json()["audit_trail"])
    assert trail1 == trail2


def test_different_request_ids_are_independent(client, loan_request):
    import uuid
    req_a = {**loan_request, "request_id": f"dedup-a-{uuid.uuid4()}"}
    req_b = {**loan_request, "request_id": f"dedup-b-{uuid.uuid4()}"}

    resp_a = client.post("/workflow/submit", json=req_a)
    resp_b = client.post("/workflow/submit", json=req_b)

    assert resp_a.json()["request_id"] != resp_b.json()["request_id"]
    # Neither should be marked as a replay
    assert resp_a.headers.get("X-Idempotent-Replay") is None
    assert resp_b.headers.get("X-Idempotent-Replay") is None
