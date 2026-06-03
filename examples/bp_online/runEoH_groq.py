import os

from eoh import eoh
from eoh.utils.getParas import Paras


def require_api_key():
    for name in ("EOH_API_KEY", "GROQ_API_KEY"):
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError("Missing API key. Set EOH_API_KEY or GROQ_API_KEY.")


def env_int(name, default):
    value = os.getenv(name)
    return int(value) if value else default


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def resolve_results_dir(output_path):
    normalized = os.path.normpath(output_path)
    if os.path.basename(normalized).lower() == "results":
        return normalized
    return os.path.join(normalized, "results")


if __name__ == "__main__":
    paras = Paras()

    output_path = os.getenv("EOH_OUTPUT_PATH", os.path.dirname(__file__))
    results_dir = resolve_results_dir(output_path)
    n_proc = env_int("EOH_N_PROC", 1)
    os.environ.setdefault("EOH_LLM_LOG", "true")
    os.environ.setdefault(
        "EOH_LLM_LOG_DIR",
        os.path.join(results_dir, "llm_logs"),
    )
    os.environ.setdefault("EOH_REASONING_EFFORT", "none")
    os.environ.setdefault("EOH_REASONING_FORMAT", "hidden")
    os.environ.setdefault("EOH_MAX_COMPLETION_TOKENS", "1200")

    paras.set_paras(
        method="eoh",
        problem="bp_online",
        llm_api_endpoint=os.getenv(
            "EOH_API_ENDPOINT",
            "https://api.groq.com/openai/v1",
        ),
        llm_api_key=require_api_key(),
        llm_model=os.getenv("EOH_MODEL", "qwen/qwen3-32b"),
        ec_pop_size=env_int("EOH_POP_SIZE", 2),
        ec_n_pop=env_int("EOH_N_POP", 2),
        exp_n_proc=n_proc,
        exp_output_path=output_path,
        exp_debug_mode=env_bool("EOH_DEBUG", False),
    )
    paras.eva_timeout = env_int("EOH_EVAL_TIMEOUT", 250)

    evolution = eoh.EVOL(paras)
    evolution.run()
