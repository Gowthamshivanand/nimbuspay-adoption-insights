"""Warm up and check the Modal endpoint from the laptop (stdlib only, Windows PowerShell 5.1 friendly).
  $env:FT_REMOTE_URL = "https://<workspace>--gowtham-nimbuspay-serve-serve-web.modal.run"
  $env:FT_REMOTE_KEY = "<the NP_SERVE_KEY you put in the Modal secret>"
  python finetune/modal/remote_check.py --wait 600          # waits for a cold start (first one can take minutes), then times 5 route calls
  python finetune/modal/remote_check.py --ping-min 30       # also ping once a minute for 30 min (keeps a scale-to-zero container awake)
The key is read from the environment and never printed."""
import argparse, json, os, sys, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)


def call(url, key, path, body=None, timeout=60):
    req = urllib.request.Request(url.rstrip("/") + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + key} if key else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)


def route_once(url, key, q="which bots are flakiest", role="platform_engineer"):
    from app import finetuned as FT
    body = {"model": os.environ.get("FT_REMOTE_MODEL", "gowtham-nimbuspay-agent-7b"), "stream": False,
            "messages": FT.route_messages(q, role), "options": {"temperature": 0, "num_predict": 96}, "format": FT.route_schema()}
    t = time.perf_counter(); out = call(url, key, "/api/chat", body, timeout=120)
    return time.perf_counter() - t, out["message"]["content"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--wait", type=int, default=600); ap.add_argument("--ping-min", type=int, default=0)
    a = ap.parse_args()
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass
    url, key = os.environ.get("FT_REMOTE_URL", ""), os.environ.get("FT_REMOTE_KEY", "")
    if not url or not key: sys.exit("Set FT_REMOTE_URL and FT_REMOTE_KEY first (see finetune/modal/README.md).")
    t0 = time.time()
    while True:
        try:
            h = call(url, "", "/health", timeout=30)
            if h.get("ready"): break
            print("container up, model still loading...", flush=True)
        except Exception as e:
            print(f"waiting for the endpoint ({int(time.time() - t0)} s): {str(e)[:80]}", flush=True)
        if time.time() - t0 > a.wait: sys.exit("Endpoint not ready in time. Check `modal app logs gowtham-nimbuspay-serve`.")
        time.sleep(10)
    print(f"ready after {time.time() - t0:.0f} s: {h}")
    lat = []
    for i in range(5):
        s, txt = route_once(url, key); lat.append(s); print(f"  route call {i + 1}: {s * 1000:.0f} ms -> {txt[:90]}")
    lat.sort(); print(f"median {lat[2] * 1000:.0f} ms (includes the internet round trip from this laptop)")
    end = time.time() + a.ping_min * 60
    while time.time() < end:
        time.sleep(60)
        try: s, _ = route_once(url, key); print(time.strftime("%H:%M"), f"ping ok {s * 1000:.0f} ms", flush=True)
        except Exception as e: print(time.strftime("%H:%M"), "ping failed:", str(e)[:80], flush=True)


if __name__ == "__main__":
    main()
