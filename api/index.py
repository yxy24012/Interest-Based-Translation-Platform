# api/index.py
from vercel_app import app  # 或者你的 app

# Vercel Python 要求有 handler 函数
def handler(request, response):
    return {
        "statusCode": 200,
        "body": "Hello Vercel!"
    }

# Flask app 也可以保留
try:
    @app.route("/healthz")
    def _healthz():
        return "ok"
except Exception:
    pass
