# examples

Runnable companion code for the things I write about. One directory per
article — each self-contained, each verified end to end on a real machine
before the article went out.

| Directory | Article | What it does |
|---|---|---|
| [`example/deepagents-sandbox`](example/deepagents-sandbox) | *Two ways to give a deepagents agent a sandbox you own* | The same twelve backend assertions and the same agent task run down both integration paths — E2B's own deepagents backend and SandrPod's — so the comparison is like for like. |
| [`example/e2b-compatible`](example/e2b-compatible) | *Self-hosting an E2B-compatible sandbox stack, from an empty server* | Takes a blank VM to a deployment the unmodified `e2b` Python SDK talks to: Docker, wildcard DNS, a wildcard certificate via DNS-01, four containers, and a 50-check acceptance sweep against the real client. |

## Conventions

- Scripts are numbered in the order you run them.
- Nothing is hardcoded to my domain or my server — everything reads from
  environment variables, and every example says which ones up front.
- Credentials go in a `*.env` file the scripts `source`; those are gitignored,
  and each example ships a `.example` template instead.
- Outputs quoted in an article come from a real run. Where a domain or an IP
  appears it has been replaced with `example.com` / `203.0.113.10`, and the
  article says so.

## Licence

Apache-2.0, matching [SandrPod](https://github.com/sandrpod/sandrpod).
