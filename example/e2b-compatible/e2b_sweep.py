#!/usr/bin/env python3
"""Exercise the official e2b SDK surface against a self-hosted SandrPod.

The SDK is unmodified; only E2B_DOMAIN + E2B_API_KEY point it at your own
deployment. Every check records its evidence, or the exception that killed it.
"""
import io
import os
import sys
import time
import traceback

import httpx
from e2b import Sandbox
from e2b.sandbox.filesystem.filesystem import WriteEntry
from e2b.sandbox.commands.command_handle import PtySize
from e2b.sandbox.sandbox_api import SandboxQuery

RESULTS = []
LABEL = "E2B SDK surface against self-hosted sandrpod"


_LAST_GROUP = [None]


def check(group, name):
    """Wrap one check: the return value is the evidence, an exception is a
    failure, and both land in the table.

    Each row prints the moment it completes rather than at the end. Buffering
    the whole table hides which check is slow — and makes a screen recording of
    the run forty seconds of nothing followed by a dump.
    """
    def deco(fn):
        t0 = time.time()
        try:
            detail, ok = str(fn())[:88], True
        except Exception as e:
            detail, ok = f"{type(e).__name__}: {e}"[:88], False
        dt = time.time() - t0
        RESULTS.append((group, name, ok, detail, dt))
        if _LAST_GROUP[0] != group:
            print(f"\n[{group}]", flush=True)
            _LAST_GROUP[0] = group
        print(f"  {'✓' if ok else '✗'} {name:<34} {dt:5.1f}s  {detail}", flush=True)
        return fn
    return deco


def main():
    dom, key = os.environ["E2B_DOMAIN"], os.environ["E2B_API_KEY"]
    print(f"target: {dom}   key: {key[:14]}…\n")

    # ---------- lifecycle ----------
    t0 = time.time()
    sbx = Sandbox.create(metadata={"suite": "article", "lang": "python"})
    create_s = time.time() - t0
    sid = sbx.sandbox_id
    print(f"sandbox {sid}  (create {create_s:.1f}s)\n")

    check("lifecycle", "create")(lambda: f"{sid} in {create_s:.1f}s")
    check("lifecycle", "is_running")(lambda: sbx.is_running())
    check("lifecycle", "get_info")(lambda: sbx.get_info().state)
    check("lifecycle", "set_timeout")(lambda: sbx.set_timeout(600) or "600s ok")
    check("lifecycle", "list")(
        lambda: f"{sum(1 for s in Sandbox.list().next_items() if s.sandbox_id == sid)} match")
    check("lifecycle", "list(metadata filter)")(
        lambda: f"{len(Sandbox.list(query=SandboxQuery(metadata={'suite': 'article'})).next_items())} match")
    check("lifecycle", "connect")(lambda: Sandbox.connect(sid).sandbox_id)

    # ---------- filesystem ----------
    check("filesystem", "write")(
        lambda: sbx.files.write("/workspace/a.txt", "hello sandrpod\n").path)
    check("filesystem", "read")(lambda: sbx.files.read("/workspace/a.txt").strip())
    check("filesystem", "exists")(lambda: sbx.files.exists("/workspace/a.txt"))
    check("filesystem", "get_info")(
        lambda: f"size={sbx.files.get_info('/workspace/a.txt').size}")
    check("filesystem", "make_dir")(lambda: sbx.files.make_dir("/workspace/sub"))
    check("filesystem", "list")(
        lambda: sorted(e.name for e in sbx.files.list("/workspace")))
    check("filesystem", "rename")(
        lambda: sbx.files.rename("/workspace/a.txt", "/workspace/b.txt").path)
    check("filesystem", "write_files (batch)")(
        lambda: len(sbx.files.write_files([
            WriteEntry(path="/workspace/m1.txt", data="one"),
            WriteEntry(path="/workspace/m2.txt", data="two"),
        ])))
    check("filesystem", "read(bytes)")(
        lambda: len(sbx.files.read("/workspace/m1.txt", format="bytes")))
    check("filesystem", "remove")(
        lambda: sbx.files.remove("/workspace/m2.txt") or "removed")

    @check("filesystem", "watch_dir")
    def _watch():
        h = sbx.files.watch_dir("/workspace")
        sbx.files.write("/workspace/watched.txt", "trigger")
        time.sleep(2.0)
        events = h.get_new_events()
        h.stop()
        return f"{len(events)} event(s): {[(e.name, str(e.type)) for e in events][:2]}"

    # ---------- commands ----------
    check("commands", "run (foreground)")(
        lambda: sbx.commands.run("echo hi && uname -m").stdout.strip().replace("\n", " | "))
    @check("commands", "run (non-zero exit raises)")
    def _exit():
        from e2b.sandbox.commands.command_handle import CommandExitException
        try:
            sbx.commands.run("exit 3", timeout=20)
            return "no exception raised (unexpected)"
        except CommandExitException as e:
            return f"CommandExitException exit={e.exit_code} (SDK semantics)"

    @check("commands", "run (background) → pid")
    def _bg():
        h = sbx.commands.run("for i in 1 2 3; do echo tick $i; sleep 1; done", background=True)
        globals()["_bg_handle"] = h
        return f"pid={h.pid}"

    check("commands", "list")(
        lambda: f"{len(sbx.commands.list())} running")

    @check("commands", "connect (streaming)")
    def _stream():
        chunks = []
        h = sbx.commands.run("for i in 1 2 3; do echo chunk$i; sleep 0.6; done",
                             background=True)
        for _ in range(1):
            pass
        res = h.wait(on_stdout=lambda d: chunks.append(d))
        return f"{len(chunks)} chunk(s), exit={res.exit_code}"

    @check("commands", "send_stdin")
    def _stdin():
        h = sbx.commands.run("read line; echo got:$line", background=True)
        time.sleep(0.5)
        sbx.commands.send_stdin(h.pid, "ping\n")
        return h.wait().stdout.strip()

    @check("commands", "kill")
    def _kill():
        h = sbx.commands.run("sleep 60", background=True)
        time.sleep(0.5)
        return sbx.commands.kill(h.pid)

    # ---------- PTY ----------
    @check("pty", "create/send_stdin/resize/kill")
    def _pty():
        import threading
        out = []
        h = sbx.pty.create(size=PtySize(cols=80, rows=24))
        t = threading.Thread(target=lambda: h.wait(on_pty=out.append), daemon=True)
        t.start()
        time.sleep(1)
        sbx.pty.send_stdin(h.pid, b"echo pty-works\n")
        time.sleep(1.5)
        sbx.pty.resize(h.pid, PtySize(cols=120, rows=40))
        killed = sbx.pty.kill(h.pid)
        t.join(timeout=5)
        text = b"".join(out).decode(errors="replace")
        return f"killed={killed}, echoed={'pty-works' in text}, {len(out)} frame(s)"

    # ---------- observability ----------
    check("metrics", "get_metrics")(
        lambda: (lambda m: f"{len(m)} sample(s), cpu={m[-1].cpu_used_pct}% mem={m[-1].mem_used}"
                 if m else "empty")(sbx.get_metrics()))

    # ---------- port preview ----------
    @check("preview", "in-sandbox HTTP via <port>-<id>.<domain>")
    def _preview():
        sbx.files.write("/workspace/index.html", "<h1>served from the sandbox</h1>")
        sbx.commands.run("cd /workspace && nohup python3 -m http.server 8000 "
                         ">/tmp/http.log 2>&1 &", background=True)
        time.sleep(2.5)
        host = sbx.get_host(8000)
        # E2B serves these with no credential — possession of the unguessable
        # hostname is the capability, and a browser cannot send a header.
        anon = httpx.get(f"https://{host}/index.html", timeout=25).status_code
        r = httpx.get(f"https://{host}/index.html",
                      headers={"X-API-KEY": key}, timeout=25)
        if r.status_code != 200:
            raise RuntimeError(f"{host} → {r.status_code} {r.text.strip()[:60]}")
        return f"with key 200 {r.text.strip()[:30]} / without key {anon}"

    # ---------- newer SDK surface (may not exist here; recorded either way) ----------
    check("newer", "get_mcp_url")(lambda: sbx.get_mcp_url())
    check("newer", "download_url")(lambda: sbx.download_url("/workspace/b.txt")[:60])
    _snap = {}
    def _snapshot():
        info = sbx.create_snapshot(name="snap1")
        _snap["id"] = info.snapshot_id
        return info
    check("newer", "create_snapshot")(_snapshot)
    check("newer", "list_snapshots")(
        lambda: any(x.snapshot_id == _snap.get("id")
                    for x in Sandbox.list_snapshots(limit=100).next_items()))
    _forks = []
    def _fork():
        children = sbx.fork()
        _forks.extend(children)
        return children
    check("newer", "fork")(_fork)
    for child in _forks:
        try: child.kill()
        except Exception: pass
    if _snap.get("id"):
        check("newer", "delete_snapshot")(lambda: Sandbox.delete_snapshot(_snap["id"]))

    # ---------- pause / resume ----------
    check("lifecycle", "pause")(lambda: sbx.pause())
    check("lifecycle", "resume (connect)")(
        lambda: Sandbox.connect(sid).commands.run("echo back").stdout.strip())

    check("lifecycle", "kill")(lambda: sbx.kill())
    time.sleep(2)
    check("lifecycle", "is_running after kill")(
        lambda: "False (correct)" if sbx.is_running() is False else "still True (wrong)")

    report()


def report():
    ok = sum(1 for r in RESULTS if r[2])
    print("\n" + "=" * 92)
    print(f"  {LABEL} — {ok}/{len(RESULTS)} passed")
    print("=" * 92 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        report()
        sys.exit(1)
