from __future__ import annotations

import io
import warnings

import pytest
from PIL import Image

from civisort import images

RV = {"X-CiviSort-Role": "reviewer"}


def _png_bytes(size=(40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (30, 90, 90)).save(buf, format="PNG")
    return buf.getvalue()


def _report(client, **extra):
    data = {"category": "pothole", "description": "Validation test hazard", "lat": "22.5190", "lng": "88.3620"}
    data.update(extra)
    return client.post("/api/reports", data=data, content_type="multipart/form-data")


def _planned_report(client):
    rid = _report(client).get_json()["id"]
    client.post(f"/api/reports/{rid}/review", json={"severity": 3, "exposure": 3, "estimated_cost": 5000, "evidence_action": "verify"}, headers=RV)
    client.post("/api/plan/save", json={"budget": 50000}, headers=RV)
    return rid


# ---- 1. corrupt / oversized images -> 400, never 500 ----

def test_truncated_png_in_report_is_400(client):
    good = _png_bytes((200, 200))
    r = _report(client, photo=(io.BytesIO(good[: len(good) // 2]), "t.png"))
    assert r.status_code == 400
    assert "corrupt" in r.get_json()["error"].lower() or "truncated" in r.get_json()["error"].lower()
    assert client.get("/api/reports?repair_status=all").get_json()["reports"] == []  # nothing saved


def test_truncated_png_in_repair_claim_is_400(client):
    rid = _planned_report(client)
    good = _png_bytes((200, 200))
    r = client.post(f"/api/reports/{rid}/claim", data={"after_photo": (io.BytesIO(good[:100]), "t.png")}, content_type="multipart/form-data")
    assert r.status_code == 400
    assert client.get(f"/api/reports/{rid}").get_json()["repair_status"] == "planned"


@pytest.mark.parametrize("payload", [b"GIF89a" + b"\x00" * 10, b"\x89PNG\r\n\x1a\n" + b"junk", b"\xff\xd8\xff" + b"x" * 20])
def test_garbage_image_headers_are_400(client, payload):
    assert _report(client, photo=(io.BytesIO(payload), "x.png")).status_code == 400


def test_dimensions_checked_before_decoding(monkeypatch):
    big = _png_bytes((3500, 3500))  # 12.25 MP > 8 MP limit; built before the spy is installed
    calls = []
    real_load = Image.Image.load

    def spy(self, *a, **k):
        calls.append(self.size)
        return real_load(self, *a, **k)

    monkeypatch.setattr(Image.Image, "load", spy)
    class Upload:
        def read(self_inner):
            return big
    with pytest.raises(images.ImageError, match="too large"):
        images.save_upload(Upload(), "unused")
    assert calls == []  # rejected from the header, never decoded


def test_decompression_bomb_is_400(client, monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = _report(client, photo=(io.BytesIO(_png_bytes((200, 200))), "b.png"))
    assert r.status_code == 400
    assert "too large" in r.get_json()["error"].lower()


def test_valid_image_still_accepted(client):
    assert _report(client, photo=(io.BytesIO(_png_bytes()), "ok.png")).status_code == 201


# ---- 2. whole-number validation ----

@pytest.mark.parametrize("field,value", [("severity", 3.9), ("exposure", 2.5), ("severity", "3.9"), ("estimated_cost", 1500.5), ("estimated_cost", "12.7"), ("severity", True), ("estimated_cost", "abc")])
def test_review_rejects_fractional_or_non_numeric(client, field, value):
    rid = _report(client).get_json()["id"]
    r = client.post(f"/api/reports/{rid}/review", json={field: value}, headers=RV)
    assert r.status_code == 400
    assert client.get(f"/api/reports/{rid}").get_json()["severity"] is None


def test_review_accepts_whole_numbers_and_numeric_strings(client):
    rid = _report(client).get_json()["id"]
    r = client.post(f"/api/reports/{rid}/review", json={"severity": "4", "exposure": 3.0, "estimated_cost": 12000, "vulnerability": 0.5}, headers=RV)
    assert r.status_code == 200
    body = r.get_json()
    assert (body["severity"], body["exposure"], body["estimated_cost"], body["vulnerability"]) == (4, 3, 12000, 0.5)


@pytest.mark.parametrize("budget", [70000.5, "7e4", "abc", True, None.__class__])
def test_budget_must_be_whole_number(client, budget):
    if budget is None.__class__:
        budget = [1]
    assert client.post("/api/plan/suggest", json={"budget": budget}).status_code == 400
    assert client.post("/api/plan/save", json={"budget": budget}, headers=RV).status_code == 400


def test_budget_whole_number_strings_ok(client):
    assert client.post("/api/plan/suggest", json={"budget": "70000"}).status_code == 200


# ---- 3. explicit booleans ----

@pytest.mark.parametrize("value", ["false", "False", "0", "off", "no", False, 0])
def test_false_values_are_false_in_scenarios(client, value):
    r = client.post("/api/plan/suggest", json={"budget": 1000, "rain": value, "night": value, "school_hours": value})
    assert r.status_code == 200
    assert r.get_json()["scenarios"] == {"rain": False, "night": False, "school_hours": False}


@pytest.mark.parametrize("value", ["true", "1", "on", "yes", True, 1])
def test_true_values_are_true_in_scenarios(client, value):
    r = client.post("/api/plan/suggest", json={"budget": 1000, "rain": value})
    assert r.get_json()["scenarios"]["rain"] is True


@pytest.mark.parametrize("value", ["maybe", "2", 2, "tru", [1], {"a": 1}])
def test_unsupported_boolean_values_rejected(client, value):
    assert client.post("/api/plan/suggest", json={"budget": 1000, "rain": value}).status_code == 400
    assert client.post("/api/plan/save", json={"budget": 1000, "night": value}, headers=RV).status_code == 400
    assert client.get("/api/reports", query_string={"rain": value if isinstance(value, str) else "maybe"}).status_code == 400
    rid = _report(client).get_json()["id"]
    assert client.post(f"/api/reports/{rid}/review", json={"school_access": value}, headers=RV).status_code == 400


def test_school_access_form_value_false_is_false(client):
    r = _report(client, school_access="false")
    assert r.status_code == 201 and r.get_json()["school_access"] == 0
    r2 = _report(client, school_access="on", lat="22.5200")
    assert r2.get_json()["school_access"] == 1
    assert _report(client, school_access="banana", lat="22.5195").status_code == 400


def test_review_school_access_false_string(client):
    rid = _report(client, school_access="on").get_json()["id"]
    r = client.post(f"/api/reports/{rid}/review", json={"school_access": "false"}, headers=RV)
    assert r.status_code == 200 and r.get_json()["school_access"] == 0
