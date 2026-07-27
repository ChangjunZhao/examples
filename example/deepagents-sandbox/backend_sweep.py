#!/usr/bin/env python3
"""Run the same deepagents backend assertions down both routes into SandrPod.

    route=e2b        langchain-e2b's E2BSandbox wrapping an e2b.Sandbox that
                     E2B_DOMAIN points at SandrPod
    route=sandrpod   langchain-sandrpod's SandrPodSandbox, native API

Same checks either way, so the two columns are comparable rather than two
separate stories.

    python backend_sweep.py e2b
    python backend_sweep.py sandrpod
"""
import inspect
import sys
import time
import uuid

RESULTS = []
_LAST = [None]


def check(name):
    def deco(fn):
        t0 = time.time()
        try:
            detail, ok = str(fn())[:76], True
        except Exception as e:
            detail, ok = f"{type(e).__name__}: {e}"[:76], False
        RESULTS.append((name, ok, detail, time.time() - t0))
        print(f"  {'✓' if ok else '✗'} {name:<30} {time.time()-t0:5.1f}s  {detail}", flush=True)
        return fn
    return deco


def open_backend(route):
    """Build the backend and return (backend, close, label)."""
    if route == "e2b":
        from e2b import Sandbox
        from langchain_e2b import E2BSandbox
        sbx = Sandbox.create()
        # SandrPod's image works out of /workspace; langchain-e2b defaults to
        # E2B's /home/user, which is not present here.
        return E2BSandbox(sandbox=sbx, workdir="/workspace"), sbx.kill, sbx.sandbox_id

    from langchain_sandrpod import SandrPodClient
    client = SandrPodClient()
    name = "backend-" + uuid.uuid4().hex[:8]
    sbx = client.create_sandbox(name)
    return sbx, (lambda: client.delete_sandbox(name)), name


def main():
    route = sys.argv[1] if len(sys.argv) > 1 else "e2b"
    from deepagents.backends.sandbox import BaseSandbox

    t0 = time.time()
    backend, close, label = open_backend(route)
    print(f"route={route}  sandbox={label}  ({time.time()-t0:.1f}s)\n")

    try:
        check("is a deepagents backend")(lambda: isinstance(backend, BaseSandbox))
        check("protocol complete")(lambda: (lambda req, have: f"{len(req & have)}/{len(req)} methods"
                                            )({m for m, _ in inspect.getmembers(BaseSandbox, inspect.isfunction)
                                               if not m.startswith("_")},
                                              {m for m, _ in inspect.getmembers(type(backend), inspect.isfunction)
                                               if not m.startswith("_")}))
        # Absolute paths throughout: langchain-e2b rejects relative ones outright
        # (`if not path.startswith("/"): invalid_path`), so this is the common
        # ground where the two routes are actually comparable.
        WD = "/workspace"
        probe = f"{WD}/probe.txt"

        def must(r, what):
            """Fail the check on an error field — several of these report
            failure in the return value rather than raising, and a sweep that
            prints those as ✓ is worse than no sweep."""
            err = getattr(r, "error", None)
            if err:
                raise RuntimeError(f"{what}: {err}")
            return r

        check("execute")(lambda: backend.execute("echo hi from the backend; uname -m").output.strip().replace("\n", " | "))
        check("write")(lambda: must(backend.write(probe, "written by the backend\n"), "write").path)
        check("read")(lambda: must(backend.read(probe), "read").file_data["content"].strip())
        check("ls")(lambda: str(must(backend.ls(WD), "ls").entries)[:60])
        check("edit")(lambda: (must(backend.edit(probe, "written", "edited"), "edit"),
                               must(backend.read(probe), "read").file_data["content"].strip())[1])
        check("glob")(lambda: must(backend.glob("*.txt", WD), "glob").matches[:3])
        check("grep")(lambda: str(must(backend.grep("edited", WD), "grep").matches[:2])[:56])

        @check("upload_files / download_files")
        def _files():
            up = backend.upload_files([(f"{WD}/up.txt", b"round trip\n")])
            if any(r.error for r in up):
                raise RuntimeError(f"upload: {[r.error for r in up]}")
            got = backend.download_files([f"{WD}/up.txt"])
            if any(r.error for r in got):
                raise RuntimeError(f"download: {[r.error for r in got]}")
            return repr(got[0].content)[:40]

        @check("relative paths")
        def _rel():
            r = backend.write("rel.txt", "x\n")
            return "rejected (absolute required)" if r.error else f"accepted → {r.path}"

        @check("execute sees what write wrote")
        def _combined():
            must(backend.write(f"{WD}/count.py", "print(sum(range(10)))\n"), "write")
            run = backend.execute("python3 count.py").output.strip()
            if "45" not in run:
                raise RuntimeError(f"execute cannot see the written file: {run[:60]!r}")
            return f"{run} — write and execute agree on the working directory"
    finally:
        close()

    ok = sum(1 for r in RESULTS if r[1])
    print(f"\n  route={route} — {ok}/{len(RESULTS)} passed\n")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
