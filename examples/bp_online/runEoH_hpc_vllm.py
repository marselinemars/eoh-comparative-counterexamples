import os

from eoh import eoh
from eoh.utils.getParas import Paras


def require_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_int(name, default):
    value = os.getenv(name)
    return int(value) if value else default


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    paras = Paras()

    output_path = os.getenv("EOH_OUTPUT_PATH", os.path.dirname(__file__))
    n_proc = env_int("EOH_N_PROC", env_int("SLURM_CPUS_PER_TASK", 4))

    paras.set_paras(
        method="eoh",
        problem="bp_online",
        llm_api_endpoint=os.getenv(
            "EOH_API_ENDPOINT",
            "http://vllm-nodeport.vllm-ns.svc.cluster.local:8000/v1",
        ),
        llm_api_key=require_env("EOH_API_KEY"),
        llm_model=os.getenv("EOH_MODEL", "Qwen3.5-122B-A10B-FP8"),
        ec_pop_size=env_int("EOH_POP_SIZE", 4),
        ec_n_pop=env_int("EOH_N_POP", 4),
        exp_n_proc=n_proc,
        exp_output_path=output_path,
        exp_debug_mode=env_bool("EOH_DEBUG", False),
    )
    paras.eva_timeout = env_int("EOH_EVAL_TIMEOUT", 250)

    evolution = eoh.EVOL(paras)
    evolution.run()
