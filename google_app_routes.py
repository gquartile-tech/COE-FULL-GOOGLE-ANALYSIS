"""
google_app_routes.py

Google CoE routes to add to app.py.

INSTRUCTIONS FOR INTEGRATION:
===============================
1. Add the TEMPLATES block entries to the existing TEMPLATES dict in app.py:

    TEMPLATES = {
        # --- existing Amazon entries ---
        "framework": ...,
        "health":    ...,
        "mastery":   ...,
        "strategy":  ...,

        # --- add these ---
        "google_health":          BASE_DIR / "templates" / "CoE_Google_Account_Health_Analysis_Templates.xlsm",
        "google_mastery":         BASE_DIR / "templates" / "CoE_Account_Mastery_Analysis_Templates.xlsm",
        "google_framework":       BASE_DIR / "templates" / "CoE_Google_Framework_Analysis_Templates.xlsm",
        "google_strategy":        BASE_DIR / "templates" / "CoE_Google_Account_Strategy_Analysis_Templates.xlsm",
        "google_implementation":  BASE_DIR / "templates" / "CoE_Google_Account_Implementation_Analysis_Templates.xlsm",
    }

    NOTE: google_mastery reuses the existing Amazon mastery template.
    Confirm template filenames match what's in your templates/ folder before deploying.

2. Add the five run_google_* functions below to app.py (after run_strategy).

3. Add the GOOGLE_AGENTS dict below to app.py (after the existing AGENTS dict).

4. Add the /google/analyze and /google/download/<filename> routes below to app.py
   (after the existing /analyze and /download routes).

5. Update the healthcheck route to include google templates if desired.

NO OTHER CHANGES needed to existing Amazon routes.
"""

# ══════════════════════════════════════════════════════════════════════════════
# 1. PASTE THESE INTO TEMPLATES DICT
# ══════════════════════════════════════════════════════════════════════════════

GOOGLE_TEMPLATES_SNIPPET = """
    "google_health":          BASE_DIR / "templates" / "CoE_Google_Account_Health_Analysis_Templates.xlsm",
    "google_mastery":         BASE_DIR / "templates" / "CoE_Account_Mastery_Analysis_Templates.xlsm",
    "google_framework":       BASE_DIR / "templates" / "CoE_Google_Framework_Analysis_Templates.xlsm",
    "google_strategy":        BASE_DIR / "templates" / "CoE_Google_Account_Strategy_Analysis_Templates.xlsm",
    "google_implementation":  BASE_DIR / "templates" / "CoE_Google_Account_Implementation_Analysis_Templates.xlsm",
"""

# ══════════════════════════════════════════════════════════════════════════════
# 2. RUN FUNCTIONS — paste into app.py after run_strategy()
# ══════════════════════════════════════════════════════════════════════════════

def run_google_health(input_path: str) -> dict:
    from reader_databricks_google import load_google_export
    from rules_engine_google_health import evaluate_all_health
    from writer_google_health import write_health_output

    tpl = TEMPLATES["google_health"]
    if not tpl.exists():
        raise FileNotFoundError(f"Google Health template not found: {tpl}")

    ctx = load_google_export(input_path)
    safe_hash = _safe_fn(ctx.hash_name or "UNKNOWN")
    results = evaluate_all_health(ctx)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{safe_hash} - Google Health Analysis - {ts}.xlsm"
    fpath = OUTPUT_DIR / fname

    write_health_output(
        template_path=str(tpl),
        output_path=str(fpath),
        results=results,
        ctx=ctx,
    )

    size = fpath.stat().st_size if fpath.exists() else 0
    if not fpath.exists() or size < MIN_OUTPUT_BYTES:
        raise RuntimeError(f"Output too small ({size} bytes) — possible template issue.")

    out = {
        "label":    "Google Health Analysis",
        "filename": fname,
        "ok":       sum(1 for r in results.values() if r.status == "OK"),
        "flag":     sum(1 for r in results.values() if r.status == "FLAG"),
        "partial":  sum(1 for r in results.values() if r.status == "PARTIAL"),
    }
    del ctx, results
    return out


def run_google_mastery(input_path: str) -> dict:
    from reader_databricks_google import load_google_export
    from rules_engine_google_mastery import evaluate_all_mastery
    from writer_google_mastery import write_mastery_output

    tpl = TEMPLATES["google_mastery"]
    if not tpl.exists():
        raise FileNotFoundError(f"Google Mastery template not found: {tpl}")

    ctx = load_google_export(input_path)
    safe_hash = _safe_fn(ctx.hash_name or "UNKNOWN")
    results = evaluate_all_mastery(ctx)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{safe_hash} - Google Mastery Analysis - {ts}.xlsm"
    fpath = OUTPUT_DIR / fname

    write_mastery_output(
        template_path=str(tpl),
        output_path=str(fpath),
        results=results,
        ctx=ctx,
    )

    size = fpath.stat().st_size if fpath.exists() else 0
    if not fpath.exists() or size < MIN_OUTPUT_BYTES:
        raise RuntimeError(f"Output too small ({size} bytes) — possible template issue.")

    out = {
        "label":    "Google Mastery Analysis",
        "filename": fname,
        "ok":       sum(1 for r in results.values() if r.status == "OK"),
        "flag":     sum(1 for r in results.values() if r.status == "FLAG"),
        "partial":  sum(1 for r in results.values() if r.status == "PARTIAL"),
    }
    del ctx, results
    return out


def run_google_framework(input_path: str) -> dict:
    from reader_databricks_google import load_google_export
    from rules_engine_google_framework import evaluate_all_framework
    from writer_google_framework import write_framework_output

    tpl = TEMPLATES["google_framework"]
    if not tpl.exists():
        raise FileNotFoundError(f"Google Framework template not found: {tpl}")

    ctx = load_google_export(input_path)
    safe_hash = _safe_fn(ctx.hash_name or "UNKNOWN")
    results = evaluate_all_framework(ctx)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{safe_hash} - Google Framework Analysis - {ts}.xlsm"
    fpath = OUTPUT_DIR / fname

    write_framework_output(
        template_path=str(tpl),
        output_path=str(fpath),
        results=results,
        ctx=ctx,
    )

    size = fpath.stat().st_size if fpath.exists() else 0
    if not fpath.exists() or size < MIN_OUTPUT_BYTES:
        raise RuntimeError(f"Output too small ({size} bytes) — possible template issue.")

    out = {
        "label":    "Google Framework Analysis",
        "filename": fname,
        "ok":       sum(1 for r in results.values() if r.status == "OK"),
        "flag":     sum(1 for r in results.values() if r.status == "FLAG"),
        "partial":  sum(1 for r in results.values() if r.status == "PARTIAL"),
    }
    del ctx, results
    return out


def run_google_strategy(input_path: str) -> dict:
    from reader_databricks_google import load_google_export
    from rules_engine_google_strategy import evaluate_all_strategy
    from writer_google_strategy import write_strategy_output

    tpl = TEMPLATES["google_strategy"]
    if not tpl.exists():
        raise FileNotFoundError(f"Google Strategy template not found: {tpl}")

    ctx = load_google_export(input_path)
    safe_hash = _safe_fn(ctx.hash_name or "UNKNOWN")
    results = evaluate_all_strategy(ctx)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{safe_hash} - Google Strategy Analysis - {ts}.xlsm"
    fpath = OUTPUT_DIR / fname

    write_strategy_output(
        template_path=str(tpl),
        output_path=str(fpath),
        results=results,
        ctx=ctx,
    )

    size = fpath.stat().st_size if fpath.exists() else 0
    if not fpath.exists() or size < MIN_OUTPUT_BYTES:
        raise RuntimeError(f"Output too small ({size} bytes) — possible template issue.")

    out = {
        "label":    "Google Strategy Analysis",
        "filename": fname,
        "ok":       sum(1 for r in results.values() if r.status == "OK"),
        "flag":     sum(1 for r in results.values() if r.status == "FLAG"),
        "partial":  sum(1 for r in results.values() if r.status == "PARTIAL"),
    }
    del ctx, results
    return out


def run_google_implementation(input_path: str) -> dict:
    from reader_databricks_google import load_google_export
    from rules_engine_google_implementation import evaluate_all_implementation
    from writer_google_implementation import write_implementation_output

    tpl = TEMPLATES["google_implementation"]
    if not tpl.exists():
        raise FileNotFoundError(f"Google Implementation template not found: {tpl}")

    ctx = load_google_export(input_path)
    safe_hash = _safe_fn(ctx.hash_name or "UNKNOWN")
    results = evaluate_all_implementation(ctx)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{safe_hash} - Google Implementation Analysis - {ts}.xlsm"
    fpath = OUTPUT_DIR / fname

    write_implementation_output(
        template_path=str(tpl),
        output_path=str(fpath),
        results=results,
        ctx=ctx,
    )

    size = fpath.stat().st_size if fpath.exists() else 0
    if not fpath.exists() or size < MIN_OUTPUT_BYTES:
        raise RuntimeError(f"Output too small ({size} bytes) — possible template issue.")

    out = {
        "label":    "Google Implementation Analysis",
        "filename": fname,
        "ok":       sum(1 for r in results.values() if r.status == "OK"),
        "flag":     sum(1 for r in results.values() if r.status == "FLAG"),
        "partial":  sum(1 for r in results.values() if r.status == "PARTIAL"),
    }
    del ctx, results
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 3. GOOGLE_AGENTS DICT — paste after the existing AGENTS dict
# ══════════════════════════════════════════════════════════════════════════════

GOOGLE_AGENTS = {
    "google_health":         run_google_health,
    "google_mastery":        run_google_mastery,
    "google_framework":      run_google_framework,
    "google_strategy":       run_google_strategy,
    "google_implementation": run_google_implementation,
}


# ══════════════════════════════════════════════════════════════════════════════
# 4. ROUTES — paste after the existing /analyze and /download routes
# ══════════════════════════════════════════════════════════════════════════════

# @app.route("/google/analyze", methods=["POST"])
# def google_analyze():
#     try:
#         return _google_analyze_inner()
#     except Exception as e:
#         traceback.print_exc()
#         return jsonify({"error": f"Server error: {str(e)}"}), 500
#
#
# def _google_analyze_inner():
#     if "file" not in request.files:
#         return jsonify({"error": "No file uploaded."}), 400
#     uploaded = request.files["file"]
#     if not uploaded.filename:
#         return jsonify({"error": "No file selected."}), 400
#     _, ext = os.path.splitext(uploaded.filename.lower())
#     if ext not in {".xlsx", ".xlsm"}:
#         return jsonify({"error": "Only .xlsx or .xlsm files accepted."}), 400
#
#     safe_name = secure_filename(uploaded.filename)
#     if not safe_name:
#         safe_name = f"google_upload_{uuid.uuid4().hex}{ext}"
#
#     input_path = str(UPLOAD_DIR / safe_name)
#
#     try:
#         uploaded.save(input_path)
#         agent_results = {}
#
#         for key, fn in GOOGLE_AGENTS.items():
#             try:
#                 agent_results[key] = {"status": "ok", **fn(input_path)}
#             except Exception as e:
#                 traceback.print_exc()
#                 agent_results[key] = {
#                     "status": "error",
#                     "label":  key.replace("_", " ").title(),
#                     "error":  str(e),
#                 }
#             finally:
#                 gc.collect()
#
#     finally:
#         try:
#             os.remove(input_path)
#         except Exception:
#             pass
#         gc.collect()
#
#     return jsonify({"agents": agent_results})
#
#
# @app.route("/google/download/<path:filename>")
# def google_download(filename):
#     from urllib.parse import unquote
#     from flask import send_file as _send_file
#     filename = unquote(filename)
#     p = OUTPUT_DIR / filename
#     if not p.exists():
#         return f"File not found: {filename}", 404
#     return _send_file(
#         str(p),
#         as_attachment=True,
#         download_name=filename,
#         mimetype="application/vnd.ms-excel.sheet.macroEnabled.12",
#     )
