"""Cost and scale calculator for the Adoption Insights Agent.

Every number is either a cited public list price (see SOURCES, checked 18 Oct 2026)
or a labelled ASSUMPTION. Nothing here is a NimbusPay figure; NimbusPay volumes and
cloud contract are unknown, so the defaults are illustrative only.
"""
import math

CHECKED = "2026-10-18"
SOURCES = {
    "S13": dict(label="OpenAI API pricing, standard tier, per 1M tokens", url="https://developers.openai.com/api/docs/pricing", checked=CHECKED),
    "S16": dict(label="AWS EC2 on-demand Linux, us-east-1 (c7i.large $0.08925/h, c7i.2xlarge $0.357/h, g5.xlarge $1.006/h); read via third-party AWS price mirrors (Vantage, CloudOptimo), not the AWS console",
                url="https://instances.vantage.sh/aws/ec2/g5.xlarge ; https://costcalc.cloudoptimo.com/aws-pricing-calculator/ec2/compare/c7i.2xlarge-vs-g5.xlarge ; https://aws.amazon.com/ec2/pricing/on-demand/", checked=CHECKED),
    "REPO": dict(label="Rules brain latency measured on synthetic data: p95 0.09 ms per question (420 asks); router prompt 2,056 chars (fix/TPM_ADDITIONS.md)", url="app/agent.py", checked=CHECKED),
}

# model key -> how it is billed and how fast it is assumed to be
MODELS = {
    "local_cpu": dict(label="Local qwen2.5:3b-instruct via Ollama on CPU (c7i.2xlarge, 8 vCPU)", kind="local", host_hour=0.357, host_src="S16",
                      p95_s=2.5, p95_basis="assumption", concurrency=1),
    "local_gpu": dict(label="Local qwen2.5:3b-instruct via Ollama on GPU (g5.xlarge, 1x A10G)", kind="local", host_hour=1.006, host_src="S16",
                      p95_s=0.4, p95_basis="assumption", concurrency=4),
    "gpt-4o-mini": dict(label="Hosted API: gpt-4o-mini ($0.15 in / $0.60 out per 1M)", kind="hosted", in_per_m=0.15, out_per_m=0.60, price_src="S13",
                        p95_s=1.2, p95_basis="assumption"),
    "gpt-6-luna": dict(label="Hosted API: gpt-6-luna ($0.10 in / $0.50 out per 1M)", kind="hosted", in_per_m=0.10, out_per_m=0.50, price_src="S13",
                       p95_s=1.2, p95_basis="assumption"),
    "gpt-5-nano": dict(label="Hosted API: gpt-5-nano ($0.05 in / $0.40 out per 1M)", kind="hosted", in_per_m=0.05, out_per_m=0.40, price_src="S13",
                       p95_s=1.5, p95_basis="assumption"),
}

DEFAULTS = dict(users=200, queries_per_user_day=5, rules_share=0.30, model="local_cpu", tokens_in=550, tokens_out=10)

ASSUMPTIONS = [
    dict(key="users", value=200, note="ASSUMPTION: named agent users in the first rollout wave; NimbusPay headcount unknown"),
    dict(key="queries_per_user_day", value=5, note="ASSUMPTION: gives 1,000 questions/day, same as fix/TPM_ADDITIONS.md"),
    dict(key="rules_share", value=0.30, note="ASSUMPTION: share answered without the LLM (guardrail refusals + exact rules matches); measure in the first live month"),
    dict(key="tokens_in", value=550, note="ASSUMPTION: router prompt 2,056 chars / ~4 chars per token = ~515 + the question (A1)"),
    dict(key="tokens_out", value=10, note="ASSUMPTION: the brain replies with one tool name"),
    dict(key="days_per_month", value=30, note="ASSUMPTION"),
    dict(key="hours_per_month", value=730, note="AWS billing convention (24 x 365 / 12)"),
    dict(key="peak_hour_share", value=0.10, note="ASSUMPTION: 10% of a day's questions arrive in the busiest hour"),
    dict(key="target_utilisation", value=0.60, note="ASSUMPTION: size model hosts to stay under 60% busy at peak"),
    dict(key="min_instances", value=2, note="ASSUMPTION: 2 model hosts minimum for availability when a local model is used (N+1)"),
    dict(key="app_host", value="1x c7i.large ($0.08925/h, S16)", note="ASSUMPTION: one small API container serves the app at these volumes; always counted"),
    dict(key="llm_p95", value="CPU 2.5 s, GPU 0.4 s, hosted 1.2-1.5 s", note="ASSUMPTION, not measured: model latency not yet benchmarked; proposed SLO is p95 <= 3 s"),
    dict(key="rules_p95_ms", value=0.09, note="MEASURED on synthetic data (REPO); rounded up to 1 ms for the estimate"),
    dict(key="production_model", value="Apache 2.0 Qwen 2.5 1.5B or 7B", note="Demo default qwen2.5:3b-instruct is research licence (no commercial use); production uses an Apache 2.0 size chosen by re-running the agent test. Host sizing assumed similar; re-benchmark (7B is slower on CPU)."),
    dict(key="concurrency", value="CPU 1, GPU 4 parallel requests per host", note="ASSUMPTION (Ollama OLLAMA_NUM_PARALLEL style); benchmark before go-live"),
]
DAYS, HOURS, PEAK, UTIL, MIN_LOCAL, APP_HOUR, RULES_P95_S = 30, 730, 0.10, 0.60, 2, 0.08925, 0.001


class CalcError(ValueError):
    pass


def calculate(users=None, queries_per_user_day=None, rules_share=None, model=None, tokens_in=None, tokens_out=None):
    p = dict(DEFAULTS)
    for k, v in dict(users=users, queries_per_user_day=queries_per_user_day, rules_share=rules_share,
                     model=model, tokens_in=tokens_in, tokens_out=tokens_out).items():
        if v is not None: p[k] = v
    if p["model"] not in MODELS: raise CalcError(f"Unknown model '{p['model']}'. Choose one of: {', '.join(MODELS)}")
    if not 0 <= p["rules_share"] <= 1: raise CalcError("rules_share must be between 0 and 1")
    for k in ("users", "queries_per_user_day", "tokens_in", "tokens_out"):
        if p[k] < 0 or p[k] > 10_000_000: raise CalcError(f"{k} must be between 0 and 10,000,000")
    m = MODELS[p["model"]]
    q_day = p["users"] * p["queries_per_user_day"]
    llm_day = q_day * (1 - p["rules_share"])
    q_month, llm_month = q_day * DAYS, llm_day * DAYS
    peak_llm_qps = llm_day * PEAK / 3600
    app_cost = APP_HOUR * HOURS
    if m["kind"] == "local":
        busy = peak_llm_qps * m["p95_s"] / m["concurrency"]          # hosts' worth of work at peak
        instances = max(MIN_LOCAL, math.ceil(busy / UTIL)) if llm_day > 0 else 0
        model_cost, token_cost = instances * m["host_hour"] * HOURS, 0.0
    else:
        instances = 0
        token_cost = llm_month * (p["tokens_in"] * m["in_per_m"] + p["tokens_out"] * m["out_per_m"]) / 1e6
        model_cost = token_cost
    monthly = app_cost + model_cost
    # p95 of the blend: if more than 5% of questions hit the LLM, the 95th percentile is an LLM answer
    p95 = m["p95_s"] if (1 - p["rules_share"]) > 0.05 else RULES_P95_S
    return dict(
        inputs=p, model_label=m["label"],
        queries_per_day=round(q_day, 1), llm_queries_per_day=round(llm_day, 1), queries_per_month=round(q_month),
        peak_llm_qps=round(peak_llm_qps, 4),
        monthly_cost_usd=round(monthly, 2), app_host_usd=round(app_cost, 2), model_cost_usd=round(model_cost, 2),
        token_cost_usd=round(token_cost, 2),
        cost_per_query_usd=round(monthly / q_month, 5) if q_month else None,
        cost_per_1000_llm_calls_tokens_usd=(round(1000 * (p["tokens_in"] * m["in_per_m"] + p["tokens_out"] * m["out_per_m"]) / 1e6, 4) if m["kind"] == "hosted" else 0.0),
        p95_latency_s=p95, p95_basis=("assumption" if p95 != RULES_P95_S else "measured (rules brain, synthetic)"),
        model_instances=instances, app_instances=1,
        note="Illustrative only. List prices, on-demand, USD, excl. tax, storage, egress and warehouse (warehouse costs are on slide 12). Not NimbusPay figures.",
    )


def meta():
    return dict(defaults=DEFAULTS, models={k: v["label"] for k, v in MODELS.items()}, assumptions=ASSUMPTIONS, sources=SOURCES,
                default_result=calculate())
