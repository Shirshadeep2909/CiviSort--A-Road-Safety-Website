"""HTTP routes for the dashboard and JSON API."""

from __future__ import annotations

import re
from pathlib import Path

from flask import Response, current_app, jsonify, render_template, request, send_from_directory

from civisort.images import ImageError, save_upload
from civisort.neighbourhood import BOUNDS
from civisort.reports import (
    ReportError,
    attach_score,
    claim_repair,
    close_repair,
    create_report,
    get_plan,
    get_report,
    list_events,
    list_reports,
    list_plans,
    merge_reports,
    possible_duplicates_for,
    ranked_reports,
    reopen_repair,
    review_report,
    save_plan,
    suggest_plan,
)
from civisort.scoring import VALID_CATEGORIES


def _role() -> str:
    role = request.headers.get("X-CiviSort-Role") or request.form.get("role") or "resident"
    return role if role in ("resident", "reviewer") else "resident"


_TRUE = {"1", "true", "on", "yes"}
_FALSE = {"0", "false", "off", "no", ""}


def parse_bool(value, label: str = "value", default: bool = False) -> bool:
    """Explicit boolean parsing; unsupported values are rejected instead of guessed."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
    raise ReportError(f"{label} must be true or false.")


def parse_int(value, label: str) -> int:
    """Whole numbers only: 3 or '3' pass; 3.9, '3.9', true and text are rejected."""
    if isinstance(value, bool):
        raise ReportError(f"{label} must be a whole number.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ReportError(f"{label} must be a whole number.")
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        return int(value.strip())
    raise ReportError(f"{label} must be a whole number.")


def parse_float(value, label: str) -> float:
    if isinstance(value, bool):
        raise ReportError(f"{label} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ReportError(f"{label} must be a number.") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ReportError(f"{label} must be a number.")
    return number


def _scenarios_from(source) -> dict[str, bool]:
    return {
        "rain": parse_bool(source.get("rain"), "Rain"),
        "night": parse_bool(source.get("night"), "Night"),
        "school_hours": parse_bool(source.get("school_hours"), "School hours"),
    }


def _scenarios() -> dict[str, bool]:
    source = request.args if request.method == "GET" else (request.get_json(silent=True) or request.form)
    return _scenarios_from(source)


def _error(exc: Exception, status: int = 400):
    return jsonify({"error": str(exc)}), status


def register_routes(app) -> None:
    @app.get("/")
    def index():
        return render_template(
            "index.html",
            bounds=BOUNDS,
            categories=VALID_CATEGORIES,
        )

    @app.get("/api/meta")
    def meta():
        return jsonify(
            {
                "bounds": BOUNDS,
                "categories": VALID_CATEGORIES,
                "synthetic": True,
                "auth_note": "Resident/Reviewer is a local demo role switch, not production authentication.",
                "scoring_note": "Weights are prototype planning assumptions. Scores are not measured accident risk.",
            }
        )

    @app.get("/api/reports")
    def api_reports():
        scenarios = _scenarios()
        filters = {
            "category": request.args.get("category") or "",
            "evidence_status": request.args.get("evidence_status") or "",
            "repair_status": request.args.get("repair_status") or "",
        }
        reports = ranked_reports(scenarios, filters)
        return jsonify({"reports": reports, "scenarios": scenarios})

    @app.get("/api/reports/<int:report_id>")
    def api_report(report_id: int):
        report = get_report(report_id)
        if not report:
            return _error(ReportError("Report not found."), 404)
        item = attach_score(report, _scenarios())
        item["events"] = list_events(report_id)
        item["linked_duplicates"] = []
        for other in list_reports():
            if other["primary_report_id"] == report_id and not other["is_primary"]:
                item["linked_duplicates"].append({
                    "id": other["id"], "public_code": other["public_code"], "category": other["category"],
                    "description": other["description"], "photo_filename": other["photo_filename"],
                    "evidence_status": other["evidence_status"], "created_at": other["created_at"],
                })
        if not report["is_primary"] and report["primary_report_id"]:
            parent = get_report(report["primary_report_id"])
            item["primary_public_code"] = parent["public_code"] if parent else None
        item["possible_duplicates"] = [
            {
                "id": d["id"],
                "public_code": d["public_code"],
                "distance_m": d["distance_m"],
                "is_primary": d["is_primary"],
                "primary_report_id": d["primary_report_id"],
                "evidence_status": d["evidence_status"],
            }
            for d in possible_duplicates_for(report)
        ]
        return jsonify(item)

    @app.post("/api/reports")
    def api_create():
        try:
            photo_name = None
            parse_bool(request.form.get("school_access"), "School access")  # validate before saving a photo
            upload = request.files.get("photo")
            if upload and upload.filename:
                photo_name = save_upload(upload, current_app.config["UPLOAD_DIR"])
            school = parse_bool(request.form.get("school_access"), "School access")
            report = create_report(
                category=request.form.get("category", ""),
                description=request.form.get("description", ""),
                lat=request.form.get("lat"),
                lng=request.form.get("lng"),
                photo_filename=photo_name,
                school_access=school,
                actor_role=_role(),
            )
            nearby = possible_duplicates_for(report)
            scored = attach_score(report, _scenarios())
            scored["possible_duplicates"] = [
                {"id": d["id"], "public_code": d["public_code"], "distance_m": d["distance_m"]}
                for d in nearby
            ]
            return jsonify(scored), 201
        except (ReportError, ImageError) as exc:
            return _error(exc)

    @app.post("/api/reports/<int:report_id>/review")
    def api_review(report_id: int):
        data = request.get_json(silent=True) or {}
        try:
            def maybe_int(key, label):
                if key not in data or data[key] in (None, ""):
                    return None
                return parse_int(data[key], label)

            def maybe_float(key, label):
                if key not in data or data[key] in (None, ""):
                    return None
                return parse_float(data[key], label)

            school = data.get("school_access")
            school_b = None if school is None else parse_bool(school, "School access")
            report = review_report(
                report_id,
                actor_role=_role(),
                severity=maybe_int("severity", "Severity"),
                exposure=maybe_int("exposure", "Exposure"),
                vulnerability=maybe_float("vulnerability", "Vulnerable-user context"),
                school_access=school_b,
                estimated_cost=maybe_int("estimated_cost", "Estimated cost"),
                evidence_action=data.get("evidence_action"),
            )
            return jsonify(attach_score(report, _scenarios()))
        except (ReportError, ValueError) as exc:
            return _error(exc)

    @app.post("/api/reports/<int:report_id>/merge")
    def api_merge(report_id: int):
        data = request.get_json(silent=True) or {}
        try:
            child = merge_reports(parse_int(data.get("child_id"), "Duplicate report id"), report_id, _role())
            return jsonify(attach_score(child, _scenarios()))
        except (ReportError, TypeError, ValueError) as exc:
            return _error(exc)

    @app.post("/api/plan/suggest")
    def api_suggest():
        data = request.get_json(silent=True) or {}
        try:
            budget = parse_int(data.get("budget", 0), "Budget")
            scenarios = _scenarios_from(data)
            return jsonify(suggest_plan(budget, scenarios))
        except (ReportError, TypeError, ValueError) as exc:
            return _error(exc)

    @app.post("/api/plan/save")
    def api_save_plan():
        data = request.get_json(silent=True) or {}
        try:
            budget = parse_int(data.get("budget", 0), "Budget")
            scenarios = _scenarios_from(data)
            return jsonify(save_plan(budget, scenarios, _role())), 201
        except (ReportError, TypeError, ValueError) as exec_err:
            return _error(exec_err)

    @app.get("/api/plans")
    def api_plans():
        return jsonify({"plans": list_plans()})

    @app.get("/api/plans/<int:plan_id>")
    def api_plan(plan_id: int):
        plan = get_plan(plan_id)
        if not plan:
            return _error(ReportError("Plan not found."), 404)
        return jsonify(plan)

    @app.post("/api/reports/<int:report_id>/claim")
    def api_claim(report_id: int):
        try:
            after_name = None
            upload = request.files.get("after_photo")
            if upload and upload.filename:
                after_name = save_upload(upload, current_app.config["UPLOAD_DIR"])
            note = request.form.get("note", "")
            return jsonify(attach_score(claim_repair(report_id, _role(), note, after_name), _scenarios()))
        except (ReportError, ImageError) as exc:
            return _error(exc)

    @app.post("/api/reports/<int:report_id>/close")
    def api_close(report_id: int):
        try:
            return jsonify(attach_score(close_repair(report_id, _role()), _scenarios()))
        except ReportError as exc:
            return _error(exc)

    @app.post("/api/reports/<int:report_id>/reopen")
    def api_reopen(report_id: int):
        data = request.get_json(silent=True) or {}
        try:
            return jsonify(attach_score(reopen_repair(report_id, _role(), data.get("reason", "")), _scenarios()))
        except ReportError as exc:
            return _error(exc)

    @app.get("/media/<path:filename>")
    def media(filename: str):
        safe = Path(filename).name
        folder = current_app.config["UPLOAD_DIR"]
        return send_from_directory(folder, safe)

    @app.errorhandler(ReportError)
    @app.errorhandler(ImageError)
    def validation_error(exc):
        return jsonify({"error": str(exc)}), 400

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify({"error": "That upload is too large. Photos must be 5 MB or smaller."}), 413

    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found."}), 404
        return Response("Not found", status=404, mimetype="text/plain")

    @app.errorhandler(405)
    def bad_method(_e):
        return jsonify({"error": "Method not allowed."}), 405

    @app.errorhandler(500)
    def server_error(_e):
        return jsonify({"error": "Unexpected server error. Your data was not changed."}), 500

    @app.get("/favicon.ico")
    def favicon():
        # Same SVG icon the page links to; browsers that request /favicon.ico get it too.
        return send_from_directory(current_app.static_folder + "/img", "favicon.svg", mimetype="image/svg+xml")

    @app.get("/healthz")
    def healthz():
        return Response("ok\n", mimetype="text/plain")
