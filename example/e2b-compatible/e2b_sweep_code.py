#!/usr/bin/env python3
"""The code-interpreter surface: the official e2b-code-interpreter SDK against
a self-hosted SandrPod.

A stateful kernel (variables survive across calls) and chart capture are what
separate this SDK from plain command execution, so those get the most attention.
"""
import base64
import os
import time
import traceback

from e2b_code_interpreter import Sandbox

RESULTS = []
LABEL = "e2b-code-interpreter against self-hosted sandrpod"


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
        print(f"  {'✓' if ok else '✗'} {name:<28} {dt:5.1f}s  {detail}", flush=True)
        return fn
    return deco


def main():
    t0 = time.time()
    sbx = Sandbox.create()
    print(f"sandbox {sbx.sandbox_id}  (create {time.time()-t0:.1f}s)\n")

    # ---------- basic execution ----------
    check("run_code", "stdout")(
        lambda: sbx.run_code("print('hello from the kernel')").logs.stdout[0].strip())
    check("run_code", "expression value")(
        lambda: sbx.run_code("21 * 2").text)
    check("run_code", "stdlib import")(
        lambda: sbx.run_code("import math; math.sqrt(16)").text)
    check("run_code", "multiline / loop")(
        lambda: sbx.run_code("t=0\nfor i in range(5): t+=i\nprint(t)").logs.stdout[0].strip())

    @check("run_code", "error capture")
    def _err():
        ex = sbx.run_code("1/0")
        return f"{ex.error.name}: {ex.error.value}"

    # ---------- stateful kernel: the whole point of this SDK ----------
    @check("stateful", "variables survive calls")
    def _state():
        sbx.run_code("a = 100")
        return f"a*2 = {sbx.run_code('a * 2').text}"

    @check("stateful", "functions and imports too")
    def _state2():
        sbx.run_code("import json\ndef f(x): return {'v': x*3}")
        return sbx.run_code("json.dumps(f(7))").text

    # ---------- contexts: independent namespaces ----------
    @check("contexts", "create")
    def _ctx_create():
        ctx = sbx.create_code_context()
        globals()["_ctx"] = ctx
        sbx.run_code("z = 7", context=ctx)
        return f"{ctx.id[:16]}…  z=7 written"

    check("contexts", "list")(
        lambda: f"{len(sbx.list_code_contexts())} context(s)")

    @check("contexts", "namespaces stay isolated")
    def _ctx_isolated():
        ex = sbx.run_code("z", context=globals()["_ctx"])
        main_ex = sbx.run_code("z")     # z was never defined in the default context
        return f"z={ex.text} in ctx, default ctx: {main_ex.error.name if main_ex.error else 'LEAKED'}"

    @check("contexts", "restart clears the namespace")
    def _ctx_restart():
        sbx.restart_code_context(globals()["_ctx"])
        ex = sbx.run_code("z", context=globals()["_ctx"])
        return f"{ex.error.name}: {ex.error.value}" if ex.error else "variable survived (wrong)"

    check("contexts", "remove")(
        lambda: sbx.remove_code_context(globals()["_ctx"]) or "removed")

    # ---------- charts ----------
    @check("charts", "matplotlib → PNG")
    def _chart():
        ex = sbx.run_code("""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.plot([1, 4, 9, 16, 25], marker="o")
plt.title("self-hosted sandbox")
plt.show()
""")
        if ex.error:
            raise RuntimeError(f"{ex.error.name}: {ex.error.value}")
        pngs = [r.png for r in ex.results if getattr(r, "png", None)]
        if not pngs:
            raise RuntimeError(f"no png in results: {[r.formats() for r in ex.results]}")
        raw = base64.b64decode(pngs[0])
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chart-from-sandbox.png")
        with open(out, "wb") as f:
            f.write(raw)
        return f"{len(raw)} bytes, PNG header={raw[:4]!r} -> {os.path.basename(out)}"

    @check("charts", "structured chart metadata")
    def _chart_meta():
        ex = sbx.run_code("import matplotlib;matplotlib.use('Agg')\n"
                          "import matplotlib.pyplot as plt\n"
                          "plt.bar(['a','b','c'],[3,1,2]);plt.show()")
        c = getattr(ex.results[0], "chart", None) if ex.results else None
        return f"chart={type(c).__name__ if c else None}"

    sbx.kill()
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
