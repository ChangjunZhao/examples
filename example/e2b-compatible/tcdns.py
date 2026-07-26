#!/usr/bin/env python3
"""Minimal DNSPod client: list / create / update records.

Standard library only — Tencent Cloud's TC3-HMAC-SHA256 signature is under 40
lines by hand, which beats installing the whole CLI for two A records and keeps
this step copy-pasteable anywhere.

    export TENCENTCLOUD_SECRET_ID=... TENCENTCLOUD_SECRET_KEY=...
    ./tcdns.py list   example.com
    ./tcdns.py upsert example.com api '203.0.113.10'
    ./tcdns.py upsert example.com '*' '203.0.113.10'
"""
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request

HOST = "dnspod.tencentcloudapi.com"
SERVICE = "dnspod"
VERSION = "2021-03-23"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def call(action: str, payload: dict) -> dict:
    sid = os.environ["TENCENTCLOUD_SECRET_ID"]
    skey = os.environ["TENCENTCLOUD_SECRET_KEY"]
    body = json.dumps(payload)
    ts = int(time.time())
    date = time.strftime("%Y-%m-%d", time.gmtime(ts))

    # 1. canonical request
    canonical = "\n".join([
        "POST", "/", "",
        f"content-type:application/json\nhost:{HOST}\n",
        "content-type;host",
        hashlib.sha256(body.encode()).hexdigest(),
    ])
    # 2. string to sign
    scope = f"{date}/{SERVICE}/tc3_request"
    to_sign = "\n".join([
        "TC3-HMAC-SHA256", str(ts), scope,
        hashlib.sha256(canonical.encode()).hexdigest(),
    ])
    # 3. derive the signing key
    k = _sign(("TC3" + skey).encode(), date)
    k = _sign(k, SERVICE)
    k = _sign(k, "tc3_request")
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()

    req = urllib.request.Request(f"https://{HOST}", data=body.encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Host", HOST)
    req.add_header("X-TC-Action", action)
    req.add_header("X-TC-Version", VERSION)
    req.add_header("X-TC-Timestamp", str(ts))
    req.add_header("Authorization",
                   f"TC3-HMAC-SHA256 Credential={sid}/{scope}, "
                   f"SignedHeaders=content-type;host, Signature={sig}")

    with urllib.request.urlopen(req, timeout=20) as r:
        resp = json.load(r)["Response"]
    if "Error" in resp:
        raise SystemExit(f"API error {resp['Error']['Code']}: {resp['Error']['Message']}")
    return resp


def records(domain: str) -> list:
    return call("DescribeRecordList", {"Domain": domain}).get("RecordList", [])


def cmd_list(domain: str) -> None:
    for r in records(domain):
        print(f"  {r['Name']:<12} {r['Type']:<6} {r['Value']:<28} "
              f"TTL={r['TTL']:<6} line={r['Line']}")


def cmd_upsert(domain: str, sub: str, value: str, rtype: str = "A") -> None:
    """Update in place when name+type already exists, else create — rerunning
    this never piles up duplicate records."""
    existing = [r for r in records(domain) if r["Name"] == sub and r["Type"] == rtype]
    base = {"Domain": domain, "SubDomain": sub, "RecordType": rtype,
            "RecordLine": "默认", "Value": value, "TTL": 600}
    if existing:
        rid = existing[0]["RecordId"]
        if existing[0]["Value"] == value:
            print(f"  {sub}.{domain} {rtype} already {value}, skipping")
            return
        call("ModifyRecord", {**base, "RecordId": rid})
        print(f"  {sub}.{domain} {rtype} {existing[0]['Value']} -> {value} (updated)")
    else:
        call("CreateRecord", base)
        print(f"  {sub}.{domain} {rtype} -> {value} (created)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    action, domain = sys.argv[1], sys.argv[2]
    if action == "list":
        cmd_list(domain)
    elif action == "upsert":
        cmd_upsert(domain, sys.argv[3], sys.argv[4],
                   sys.argv[5] if len(sys.argv) > 5 else "A")
    else:
        raise SystemExit(__doc__)
