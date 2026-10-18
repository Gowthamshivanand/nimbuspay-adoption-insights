.PHONY: install run test test-ui data docker
install:   ; pip install -r requirements.txt
run:       ; python -m app
test:      ; python -m pytest -q tests/test_pipeline.py tests/test_agent.py tests/test_probes.py tests/test_persona.py tests/test_api.py tests/test_features.py tests/test_brain.py && python tools/eval_agent.py --brain rules
test-ui:   ; python -m pytest -q tests/test_ui_playwright.py
data:      ; python tools/export_workbook.py && python tools/make_scenarios.py
docker:    ; docker build -t nimbuspay-insights . && docker run --rm -p 8000:8000 nimbuspay-insights
