{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "version": 2,
  "regions": ["hnd1"],
  "routes": [
    { "src": "/static/(.*)", "dest": "/static/$1",
      "headers": { "Cache-Control": "public, max-age=31536000, immutable" } }
  ],
  "env": { "PYTHONPATH": "." }
}
