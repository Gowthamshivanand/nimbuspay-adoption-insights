# Free CPU Docker Space on Hugging Face (also runs anywhere Docker runs).
# Rules brain by default: no model, no API key, no secrets baked in. Synthetic data only.
FROM python:3.12-slim
RUN useradd -m -u 1000 user
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user app ./app
# Files the app reads outside app/: metric dictionary ("Explain this number", /api/lineage) and the rules eval behind the Models tab.
COPY --chown=user src/data.json ./src/data.json
COPY --chown=user tools ./tools
COPY --chown=user tests/data/probes.json ./tests/data/probes.json
USER user
# HF Spaces routes traffic to app_port (7860, see README front-matter). The audit log lives in /tmp (writable, resets on restart).
ENV HOST=0.0.0.0 PORT=7860 NP_BRAIN=rules AUDIT_DB=/tmp/nimbuspay_audit.db PYTHONUNBUFFERED=1
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/api/health',timeout=4).status==200 else 1)"
CMD ["python", "-m", "app"]
