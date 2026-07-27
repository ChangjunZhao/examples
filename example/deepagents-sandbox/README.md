# Two deepagents backends, one sandbox you own

Companion code for *"Two ways to give a deepagents agent a sandbox you own"*.
The same assertions and the same agent task run down both integration paths, so
the two columns in the article are comparable rather than two separate stories.

Verified against a live SandrPod v0.5.3 deployment with `deepagents` 0.6.12,
`langchain-e2b` 0.0.6 and `langchain-sandrpod` 0.2.7: **12/12 backend
assertions and 3/3 agent runs down each route**.

## The two routes

| | Package | Reaches SandrPod via |
|---|---|---|
| 1 | `langchain-e2b` (E2B's own) | an `e2b.Sandbox` that `E2B_DOMAIN` points at your deployment |
| 2 | `langchain-sandrpod` | the native API |

They install into one virtualenv together if you want to compare side by side;
separate ones keep the versions unambiguous.

## Run it

```bash
python -m venv .e2b && .e2b/bin/pip install -r requirements-e2b.txt
python -m venv .sp  && .sp/bin/pip  install -r requirements-sandrpod.txt

# route 1 talks to SandrPod through the E2B wire protocol
export E2B_DOMAIN=your-domain
export E2B_API_KEY=e2b_...            # sandrpod-cli token create

# route 2 talks to it natively
export SANDRPOD_API_URL=https://api.your-domain
export SANDRPOD_API_TOKEN=...

.e2b/bin/python backend_sweep.py e2b        # 12 assertions
.sp/bin/python  backend_sweep.py sandrpod   # the same 12

# a real agent, verified by re-running its script in the container
export OPENAI_API_KEY=... OPENAI_BASE_URL=... MODEL_NAME=...
.e2b/bin/python agent_run.py e2b
.sp/bin/python  agent_run.py sandrpod
```

## Two things that will bite you on route 1

**`workdir`.** `langchain-e2b` defaults to `/home/user`, E2B's image convention.
SandrPod's image uses `/workspace` and has no `/home/user`, so pass
`workdir="/workspace"`. Before SandrPod v0.5.3 the resulting error blamed the
shell (`fork/exec /bin/bash: no such file or directory`) rather than the
directory.

**Absolute paths.** `langchain-e2b` rejects relative ones outright —
`if not path.startswith("/"): invalid_path`. That is its documented contract,
not a SandrPod limitation.

## A note on how these are written

Several backend calls report failure in a **return value** rather than by
raising: `ReadResult(error="file_not_found", file_data=None)` comes back from a
call that did not throw. The first version of `backend_sweep.py` printed those
as passes. Every check here fails on a populated `error` field, and
`agent_run.py` verifies the agent's answer by re-running its script inside the
container instead of reading what the model claimed.

---

SandrPod: <https://github.com/sandrpod/sandrpod> · Apache-2.0
