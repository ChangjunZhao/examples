#!/usr/bin/env python3
"""Give a real deepagents agent a job, down either route into SandrPod.

Same model, same prompt, same verification either way — so the two runs are
comparable. The agent has to actually use the sandbox: the check afterwards
reads the file back out of the container rather than trusting what the model
says it did.

    python agent_run.py e2b
    python agent_run.py sandrpod
"""
import os
import sys
import time
import uuid

TASK = """Write a Python script at /workspace/primes.py that prints the sum of
all prime numbers below 1000, one number per run. Then run it and tell me the
number it printed. Use absolute paths for every file operation."""

EXPECTED = "76127"          # sum of primes < 1000


def open_backend(route):
    if route == "e2b":
        from e2b import Sandbox
        from langchain_e2b import E2BSandbox
        sbx = Sandbox.create()
        # SandrPod's image works out of /workspace; langchain-e2b defaults to
        # E2B's /home/user, which does not exist here.
        return E2BSandbox(sandbox=sbx, workdir="/workspace"), sbx.kill, sbx.sandbox_id

    from langchain_sandrpod import SandrPodClient
    client = SandrPodClient()
    name = "agent-" + uuid.uuid4().hex[:8]
    return client.create_sandbox(name), (lambda: client.delete_sandbox(name)), name


def main():
    route = sys.argv[1] if len(sys.argv) > 1 else "e2b"
    from deepagents import create_deep_agent
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model=os.environ.get("MODEL_NAME", "deepseek-v4-flash"),
        base_url=os.environ["OPENAI_BASE_URL"],
        api_key=os.environ["OPENAI_API_KEY"],
        temperature=0,
    )

    t0 = time.time()
    backend, close, label = open_backend(route)
    setup = time.time() - t0
    print(f"route={route}  sandbox={label}  (setup {setup:.1f}s)\n")

    try:
        agent = create_deep_agent(model=model, backend=backend)
        t1 = time.time()
        result = agent.invoke({"messages": [{"role": "user", "content": TASK}]})
        elapsed = time.time() - t1

        msgs = result["messages"]
        answer = msgs[-1].content
        tool_calls = [c["name"] for m in msgs for c in (getattr(m, "tool_calls", None) or [])]
        print(f"turns={len(msgs)}  tools={tool_calls}")
        print(f"answer: {str(answer)[:200]}\n")

        # Verify against the container, not against what the model claims.
        listing = backend.execute("ls -l /workspace/primes.py").output.strip()
        rerun = backend.execute("python3 /workspace/primes.py").output.strip()

        print(f"  file on disk : {listing[:70]}")
        print(f"  rerun output : {rerun[:70]}")
        print(f"  correct      : {EXPECTED in rerun}")
        print(f"  said so too  : {EXPECTED in str(answer)}")
        print(f"\n  route={route}  setup {setup:.1f}s + agent {elapsed:.1f}s")
        return 0 if EXPECTED in rerun else 1
    finally:
        close()


if __name__ == "__main__":
    sys.exit(main())
