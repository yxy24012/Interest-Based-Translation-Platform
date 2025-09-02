# api/index.py
try:
    from vercel_app import app
except Exception:
    from app import app

try:
    @app.route("/healthz")
    def _healthz():
        return "ok"
except Exception:
    pass
