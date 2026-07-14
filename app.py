"""
app.py — Google CoE Full Analysis Tool
Flask backend for the Google Ads CoE agent suite.
5 pillars: Health, Mastery, Framework, Strategy, Implementation
Run:  python app.py
Open: http://127.0.0.1:8500
"""

from __future__ import annotations

import gc
import os
import re
import sys
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.resolve()
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

TEMPLATES = {
    "google_health":          BASE_DIR / "templates" / "CoE_Google_Account_Health_Analysis_Templates.xlsm",
    "google_mastery":         BASE_DIR / "templates" / "CoE_Account_Mastery_Analysis_Templates.xlsm",
    "google_framework":       BASE_DIR / "templates" / "CoE_Google_Framework_Analysis_Templates.xlsm",
    "google_strategy":        BASE_DIR / "templates" / "CoE_Google_Account_Strategy_Analysis_Templates.xlsm",
    "google_implementation":  BASE_DIR / "templates" / "CoE_Google_Account_Implementation_Analysis_Templates.xlsm",
}

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(BASE_DIR))

MIN_OUTPUT_BYTES = 5_000

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


def _safe_fn(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[^a-zA-Z0-9 \-_]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "UNKNOWN_ACCOUNT"


# ── Agent runners ─────────────────────────────────────────────────────────────

def run_google_health(input_path: str) -> dict:
    from reader_databricks_google import load_google_export
    from rules_engine_google_health import evaluate_all_health
    from writer_google_health import write_health_output

    tpl = TEMPLATES["google_health"]
    if not tpl.exists():
        raise FileNotFoundError(f"Template not found: {tpl}")

    ctx = load_google_export(input_path)
    safe_hash = _safe_fn(ctx.hash_name or "UNKNOWN")
    results = evaluate_all_health(ctx)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{safe_hash} - Google Health Analysis - {ts}.xlsm"
    fpath = OUTPUT_DIR / fname

    write_health_output(template_path=str(tpl), output_path=str(fpath), results=results, ctx=ctx)

    size = fpath.stat().st_size if fpath.exists() else 0
    if not fpath.exists() or size < MIN_OUTPUT_BYTES:
        raise RuntimeError(f"Output file too small ({size} bytes) — possible template issue.")

    out = {
        "label":   "Google Health Analysis",
        "filename": fname,
        "ok":      sum(1 for r in results.values() if r.status == "OK"),
        "flag":    sum(1 for r in results.values() if r.status == "FLAG"),
        "partial": sum(1 for r in results.values() if r.status == "PARTIAL"),
    }
    del ctx, results
    return out


def run_google_mastery(input_path: str) -> dict:
    from reader_databricks_google import load_google_export
    from rules_engine_google_mastery import evaluate_all_mastery
    from writer_google_mastery import write_mastery_output

    tpl = TEMPLATES["google_mastery"]
    if not tpl.exists():
        raise FileNotFoundError(f"Template not found: {tpl}")

    ctx = load_google_export(input_path)
    safe_hash = _safe_fn(ctx.hash_name or "UNKNOWN")
    results = evaluate_all_mastery(ctx)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{safe_hash} - Google Mastery Analysis - {ts}.xlsm"
    fpath = OUTPUT_DIR / fname

    write_mastery_output(template_path=str(tpl), output_path=str(fpath), results=results, ctx=ctx)

    size = fpath.stat().st_size if fpath.exists() else 0
    if not fpath.exists() or size < MIN_OUTPUT_BYTES:
        raise RuntimeError(f"Output file too small ({size} bytes) — possible template issue.")

    out = {
        "label":   "Google Mastery Analysis",
        "filename": fname,
        "ok":      sum(1 for r in results.values() if r.status == "OK"),
        "flag":    sum(1 for r in results.values() if r.status == "FLAG"),
        "partial": sum(1 for r in results.values() if r.status == "PARTIAL"),
    }
    del ctx, results
    return out


def run_google_framework(input_path: str) -> dict:
    from reader_databricks_google import load_google_export
    from rules_engine_google_framework import evaluate_all_framework
    from writer_google_framework import write_framework_output

    tpl = TEMPLATES["google_framework"]
    if not tpl.exists():
        raise FileNotFoundError(f"Template not found: {tpl}")

    ctx = load_google_export(input_path)
    safe_hash = _safe_fn(ctx.hash_name or "UNKNOWN")
    results = evaluate_all_framework(ctx)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{safe_hash} - Google Framework Analysis - {ts}.xlsm"
    fpath = OUTPUT_DIR / fname

    write_framework_output(template_path=str(tpl), output_path=str(fpath), results=results, ctx=ctx)

    size = fpath.stat().st_size if fpath.exists() else 0
    if not fpath.exists() or size < MIN_OUTPUT_BYTES:
        raise RuntimeError(f"Output file too small ({size} bytes) — possible template issue.")

    out = {
        "label":   "Google Framework Analysis",
        "filename": fname,
        "ok":      sum(1 for r in results.values() if r.status == "OK"),
        "flag":    sum(1 for r in results.values() if r.status == "FLAG"),
        "partial": sum(1 for r in results.values() if r.status == "PARTIAL"),
    }
    del ctx, results
    return out


def run_google_strategy(input_path: str) -> dict:
    from reader_databricks_google import load_google_export
    from rules_engine_google_strategy import evaluate_all_strategy
    from writer_google_strategy import write_strategy_output

    tpl = TEMPLATES["google_strategy"]
    if not tpl.exists():
        raise FileNotFoundError(f"Template not found: {tpl}")

    ctx = load_google_export(input_path)
    safe_hash = _safe_fn(ctx.hash_name or "UNKNOWN")
    results = evaluate_all_strategy(ctx)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{safe_hash} - Google Strategy Analysis - {ts}.xlsm"
    fpath = OUTPUT_DIR / fname

    write_strategy_output(template_path=str(tpl), output_path=str(fpath), results=results, ctx=ctx)

    size = fpath.stat().st_size if fpath.exists() else 0
    if not fpath.exists() or size < MIN_OUTPUT_BYTES:
        raise RuntimeError(f"Output file too small ({size} bytes) — possible template issue.")

    out = {
        "label":   "Google Strategy Analysis",
        "filename": fname,
        "ok":      sum(1 for r in results.values() if r.status == "OK"),
        "flag":    sum(1 for r in results.values() if r.status == "FLAG"),
        "partial": sum(1 for r in results.values() if r.status == "PARTIAL"),
    }
    del ctx, results
    return out


def run_google_implementation(input_path: str) -> dict:
    from reader_databricks_google import load_google_export
    from rules_engine_google_implementation import evaluate_all_implementation
    from writer_google_implementation import write_implementation_output

    tpl = TEMPLATES["google_implementation"]
    if not tpl.exists():
        raise FileNotFoundError(f"Template not found: {tpl}")

    ctx = load_google_export(input_path)
    safe_hash = _safe_fn(ctx.hash_name or "UNKNOWN")
    results = evaluate_all_implementation(ctx)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{safe_hash} - Google Implementation Analysis - {ts}.xlsm"
    fpath = OUTPUT_DIR / fname

    write_implementation_output(template_path=str(tpl), output_path=str(fpath), results=results, ctx=ctx)

    size = fpath.stat().st_size if fpath.exists() else 0
    if not fpath.exists() or size < MIN_OUTPUT_BYTES:
        raise RuntimeError(f"Output file too small ({size} bytes) — possible template issue.")

    out = {
        "label":   "Google Implementation Analysis",
        "filename": fname,
        "ok":      sum(1 for r in results.values() if r.status == "OK"),
        "flag":    sum(1 for r in results.values() if r.status == "FLAG"),
        "partial": sum(1 for r in results.values() if r.status == "PARTIAL"),
    }
    del ctx, results
    return out


AGENTS = {
    "google_health":         run_google_health,
    "google_mastery":        run_google_mastery,
    "google_framework":      run_google_framework,
    "google_strategy":       run_google_strategy,
    "google_implementation": run_google_implementation,
}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        return _analyze_inner()
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Server error: {str(e)}"}), 500


def _analyze_inner():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400
    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "No file selected."}), 400
    _, ext = os.path.splitext(uploaded.filename.lower())
    if ext not in {".xlsx", ".xlsm"}:
        return jsonify({"error": "Only .xlsx or .xlsm files accepted."}), 400

    safe_name = secure_filename(uploaded.filename)
    if not safe_name:
        safe_name = f"upload_{uuid.uuid4().hex}{ext}"

    input_path = str(UPLOAD_DIR / safe_name)

    try:
        uploaded.save(input_path)
        agent_results = {}

        # Sequential execution — avoids Gunicorn worker timeout on Render
        for key, fn in AGENTS.items():
            try:
                agent_results[key] = {"status": "ok", **fn(input_path)}
            except Exception as e:
                traceback.print_exc()
                agent_results[key] = {
                    "status": "error",
                    "label":  key.replace("_", " ").title(),
                    "error":  str(e),
                }
            finally:
                gc.collect()

    finally:
        try:
            os.remove(input_path)
        except Exception:
            pass
        gc.collect()

    return jsonify({"agents": agent_results})


@app.route("/download/<path:filename>")
def download(filename):
    from urllib.parse import unquote
    filename = unquote(filename)
    p = OUTPUT_DIR / filename

    if not p.exists():
        return f"File not found: {filename}", 404

    return send_file(
        str(p),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.ms-excel.sheet.macroEnabled.12",
    )


@app.route("/healthcheck")
def healthcheck():
    missing = [k for k, p in TEMPLATES.items() if not p.exists()]
    ok = len(missing) == 0
    return jsonify({
        "status":            "ok" if ok else "degraded",
        "missing_templates": missing,
    }), 200 if ok else 503


@app.route("/favicon.ico")
def favicon():
    return "", 204


if __name__ == "__main__":
    print("\n  Google CoE Full Analysis Tool")
    print("  ─────────────────────────────────────────────────")
    for k, p in TEMPLATES.items():
        print(f"  [{k:25s}] {'✓' if p.exists() else '✗ MISSING'} {p.name}")
    print("  Open → http://127.0.0.1:8500\n")
    app.run(host="127.0.0.1", port=8500, debug=True)
