"""Run: python -m app  (then open http://127.0.0.1:8000)"""
import os, uvicorn
if __name__ == "__main__":
    uvicorn.run("app.server:app", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
