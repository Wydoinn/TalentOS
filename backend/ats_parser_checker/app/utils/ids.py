from uuid import uuid4


def _prefixed_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def generate_candidate_id() -> str:
    return _prefixed_id("cand")


def generate_report_run_id() -> str:
    return _prefixed_id("run")
