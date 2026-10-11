#!/usr/bin/env python3
"""Prove a running Pulse stack works, end to end, and survives its dependencies failing.

    python3 scripts/doctor.py --compose "docker compose -f docker-compose.prod.yml" \
        --api-service api --base http://localhost:8080 --mail http://localhost:8025

Normally run through `make doctor`, which boots the stack, runs this, collects logs on
failure and tears down. Stdlib only. Prints PASS/FAIL per check and exits non-zero on any
failure. Needs the demo data (SEED_DEMO=1), Mailpit as the SMTP sink, and Docker access for
the drills.

What it checks
  1  liveness, readiness (database + redis), the SPA, the API through nginx
  2  sign-in (and a wrong password); create a service through the API
  3  alert -> incident (multi-line summary) -> page lands in the inbox with a one-line subject
  4  duplicate alert attaches to the one open incident
  5  an unanswered page escalates to level 2 on its own (worker + beat + broker wired up)
  6  acknowledge and resolve; the timeline tells the story
  7  forged X-Forwarded-For prefixes do not reset the login throttle
  8  drills: redis down, workers restarted, database down, API workers SIGKILLed and the
     API process exiting on its own (a `docker kill` is a manual stop, so it is not used)
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

RESULTS: list[tuple[str, bool, str]] = []
T0 = time.time()


def say(msg: str) -> None:
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    say(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return ok


class Session:
    """A cookie-keeping API client that speaks Django's CSRF protocol."""

    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method: str, path: str, body=None, headers=None, timeout=15):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        token = next((c.value for c in self.jar if c.name == "csrftoken"), None)
        if token and method not in ("GET", "HEAD"):
            req.add_header("X-CSRFToken", token)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as err:
            raw, status = err.read(), err.code
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as err:
            return 0, {"error": str(err)}
        try:
            return status, json.loads(raw) if raw else None
        except ValueError:
            return status, raw.decode(errors="replace")

    def login(self, email: str, password: str, headers=None):
        self.call("GET", "/api/v1/auth/csrf/")
        return self.call(
            "POST", "/api/v1/auth/login/", {"email": email, "password": password}, headers
        )


def wait_for(fn, timeout: float, every: float = 2.0):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = fn()
        if last:
            return last
        time.sleep(every)
    return last


class Doctor:
    def __init__(self, args: argparse.Namespace) -> None:
        self.a = args
        self.compose = shlex.split(args.compose)
        self.api = Session(args.base)
        self.mail = args.mail.rstrip("/")
        self.service: dict = {}
        self.key = ""

    # --- helpers -----------------------------------------------------------------------
    def dc(self, *cmd: str) -> bool:
        proc = subprocess.run(
            [*self.compose, *cmd], capture_output=True, text=True, timeout=180, check=False
        )
        if proc.returncode:
            say(f"docker compose {' '.join(cmd)} failed: {proc.stderr.strip()[-300:]}")
        return proc.returncode == 0

    def mails(self) -> list[dict]:
        req = urllib.request.Request(f"{self.mail}/api/v1/messages?limit=500")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())["messages"]

    def clear_mail(self) -> None:
        req = urllib.request.Request(f"{self.mail}/api/v1/messages", method="DELETE")
        urllib.request.urlopen(req, timeout=10).read()

    def mail_counts(self, number: int) -> Counter:
        """recipient -> number of mails whose subject names incident #number."""
        counts: Counter = Counter()
        for m in self.mails():
            if f"#{number} " in m["Subject"]:
                for to in m["To"]:
                    counts[to["Address"]] += 1
        return counts

    def trigger(self, summary: str, key: str | None = None):
        body = {
            "routing_key": self.key,
            "event_action": "trigger",
            "payload": {"summary": summary, "severity": "critical", "source": "doctor"},
        }
        if key:
            body["dedup_key"] = key
        return Session(self.a.base).call("POST", "/api/v1/events/", body)

    def timeline(self, incident_id: int) -> list[str]:
        status, body = self.api.call("GET", f"/api/v1/incidents/{incident_id}/timeline/")
        if status != 200:
            return []
        return [e["type"] for e in reversed(body["results"])]

    def ready(self):
        return Session(self.a.base).call("GET", "/readyz", timeout=5)

    # --- checks ------------------------------------------------------------------------
    def basics(self) -> None:
        anon = Session(self.a.base)
        status, body = anon.call("GET", "/healthz")
        check("liveness /healthz", status == 200 and body == {"status": "ok"}, f"{status}")
        status, body = self.ready()
        ok = status == 200 and isinstance(body, dict) and body.get("status") == "ok"
        check("readiness /readyz checks database and redis", ok, json.dumps(body))
        status, body = anon.call("GET", "/")
        check("SPA is served", status == 200 and 'id="root"' in str(body), f"{status}")
        with urllib.request.urlopen(self.a.base + "/", timeout=10) as resp:
            hdr = {k.lower(): v for k, v in resp.headers.items()}
        check(
            "SPA is served with nosniff, frame and referrer headers",
            hdr.get("x-content-type-options") == "nosniff"
            and hdr.get("x-frame-options") == "DENY"
            and "referrer-policy" in hdr,
        )
        csp = hdr.get("content-security-policy", "")
        check(
            "SPA enforces a Content-Security-Policy (scripts from self only) and Permissions-Policy",
            "script-src 'self'" in csp
            and "frame-ancestors 'none'" in csp
            and "camera=()" in hdr.get("permissions-policy", ""),
            csp[:120],
        )
        try:
            urllib.request.urlopen(self.a.base + "/a/not-a-real-token/", timeout=10)
            link_status, link_body = 200, ""
        except urllib.error.HTTPError as exc:
            link_status, link_body = exc.code, exc.read().decode(errors="replace")
        check(
            "one-tap action links reach Django through nginx (not the SPA)",
            link_status == 404 and "Link not valid" in link_body,
            f"{link_status}",
        )
        status, _ = anon.call("GET", "/api/v1/incidents/")
        check("API is reachable through the proxy and refuses anonymous callers", status == 403)

    def sign_in(self) -> bool:
        bad = Session(self.a.base)
        status, _ = bad.login("admin@demo.local", "not-the-password")
        check("wrong password is refused", status == 401, f"{status}")
        status, body = self.api.login("admin@demo.local", "demo1234")
        if not check("admin signs in (needs SEED_DEMO=1)", status == 200, f"{status}"):
            return False
        status, body = self.api.call("GET", "/api/v1/services/")
        template = next((s for s in body["results"] if s["name"] == "checkout-api"), None)
        if not check("seeded services are visible", template is not None):
            return False
        name = f"doctor-{int(time.time())}"
        status, svc = self.api.call(
            "POST",
            "/api/v1/services/",
            {
                "team": template["team"],
                "name": name,
                "description": "created by scripts/doctor.py",
                "escalation_policy": template["escalation_policy"],
            },
        )
        if not check("service created through the API", status == 201, f"{status}"):
            return False
        self.service, self.key = svc, svc["integration_key"]
        return True

    def alert_flow(self) -> None:
        self.clear_mail()
        status, body = self.trigger("Disk full\non db-1\r\n(95%)", key="doctor-main")
        if not check("alert accepted (202)", status == 202 and body["status"] == "accepted"):
            return
        inc = body["incident_id"]
        status, dup = self.trigger("Disk full again", key="doctor-main")
        check(
            "duplicate alert attaches to the same incident",
            status == 202 and dup["incident_id"] == inc,
            f"{inc} vs {dup and dup.get('incident_id')}",
        )
        status, detail = self.api.call("GET", f"/api/v1/incidents/{inc}/")
        number = detail["number"] if status == 200 else -1
        check(
            "incident opened with a one-line title",
            status == 200
            and detail["status"] == "triggered"
            and "\n" not in detail["title"]
            and detail["alert_count"] == 2,
            repr(detail.get("title")) if status == 200 else str(status),
        )
        l0 = wait_for(lambda: self.mail_counts(number), 25, 1)
        check("page reaches the inbox (Mailpit) exactly once", bool(l0) and set(l0.values()) == {1},
              json.dumps(dict(l0 or {})))
        subjects = [m["Subject"] for m in self.mails() if f"#{number} " in m["Subject"]]
        check("email subject is a single line", bool(subjects) and all("\n" not in s for s in subjects),
              repr(subjects[:1]))

        say("waiting for the level-1 page to go unanswered and escalate (about a minute)...")
        got = wait_for(lambda: "escalated" in self.timeline(inc), 140, 3)
        check("unanswered page escalates on its own (worker + beat + broker)", bool(got))
        l1 = wait_for(lambda: len(self.mail_counts(number)) > len(l0 or {}), 30, 2)
        counts = self.mail_counts(number)
        check("level-2 responders are emailed, nobody twice", bool(l1) and set(counts.values()) == {1},
              json.dumps(dict(counts)))

        status, _ = self.api.call("POST", f"/api/v1/incidents/{inc}/acknowledge/")
        check("acknowledge", status == 200, f"{status}")
        status, _ = self.api.call("POST", f"/api/v1/incidents/{inc}/resolve/")
        check("resolve", status == 200, f"{status}")
        story = [t for t in self.timeline(inc) if t != "notified"]
        check(
            "timeline tells the story",
            story[:2] == ["triggered", "alert_attached"] and story[-2:] == ["acknowledged", "resolved"]
            and "escalated" in story,
            " -> ".join(story),
        )

    def throttle_spoof(self) -> None:
        s = Session(self.a.base)
        codes = []
        for i in range(13):
            status, _ = s.login(
                "nobody@example.test", "x", headers={"X-Forwarded-For": f"10.9.8.{i}, 198.51.100.1"}
            )
            codes.append(status)
        check(
            "forged X-Forwarded-For prefixes do not reset the login throttle",
            codes[-1] == 429,
            f"statuses {codes}",
        )

    # --- drills ------------------------------------------------------------------------
    def new_incident(self, label: str):
        status, body = self.trigger(f"drill: {label}", key=f"drill-{label}-{int(time.time())}")
        if status != 202:
            return None, -1
        status, detail = self.api.call("GET", f"/api/v1/incidents/{body['incident_id']}/")
        return body["incident_id"], detail["number"] if status == 200 else -1

    def settled(self, inc: int, number: int, label: str, limit: int = 240) -> None:
        """The incident escalated, and every page that was owed arrived exactly once."""
        esc = wait_for(lambda: "escalated" in self.timeline(inc), limit, 3)
        check(f"{label}: incident still escalates", bool(esc))

        def owed():
            c = self.mail_counts(number)
            return c if len(c) >= 2 else None

        counts = wait_for(owed, limit, 3)
        check(
            f"{label}: every page arrives, none twice",
            bool(counts) and set(counts.values()) == {1},
            json.dumps(dict(counts or {})),
        )
        status, _ = self.api.call("POST", f"/api/v1/incidents/{inc}/resolve/")
        check(f"{label}: incident resolves afterwards", status == 200, f"{status}")

    def drill_redis(self) -> None:
        say("drill 1: redis down")
        self.clear_mail()
        if not self.dc("stop", "redis"):
            check("drill redis: stop", False)
            return
        time.sleep(3)
        status, body = self.ready()
        check(
            "redis down: /readyz says degraded (200), not unavailable",
            status == 200 and body.get("status") == "degraded",
            f"{status} {body}",
        )
        inc, number = self.new_incident("redis")
        check("redis down: the API still accepts an alert and commits the incident", inc is not None)
        self.dc("start", "redis")
        ok = wait_for(lambda: self.ready()[0] == 200 and self.ready()[1].get("status") == "ok", 60, 2)
        check("redis back: /readyz returns to ok", bool(ok))
        if inc is not None:
            self.settled(inc, number, "after redis outage")

    def drill_worker(self) -> None:
        say("drill 2: workers restarted mid-escalation")
        self.clear_mail()
        inc, number = self.new_incident("worker")
        if inc is None:
            check("worker drill: incident opened", False)
            return
        time.sleep(2)
        self.dc("restart", "worker", "worker-escalations")
        self.settled(inc, number, "after worker restart")

    def drill_db(self) -> None:
        say("drill 3: database down")
        if not self.dc("stop", "db"):
            check("drill db: stop", False)
            return
        time.sleep(4)
        status, body = self.ready()
        check("db down: /readyz is 503", status == 503 and body.get("status") == "unavailable",
              f"{status}")
        status, _ = Session(self.a.base).call("GET", "/healthz")
        check("db down: /healthz stays 200 (no restart storm)", status == 200)
        status, _ = self.trigger("while the database is down")
        check("db down: the API fails cleanly (a 5xx, no hang)", status >= 500, f"{status}")
        self.dc("start", "db")
        ok = wait_for(lambda: self.ready()[0] == 200 and self.ready()[1].get("status") == "ok", 90, 2)
        check("db back: /readyz recovers with no manual step", bool(ok))
        status, body = self.trigger("after the database came back", key="drill-db-after")
        check("db back: alerts are accepted again", status == 202, f"{status}")
        if status == 202:
            self.api.call("POST", f"/api/v1/incidents/{body['incident_id']}/resolve/")

    def api_up(self, timeout: int = 90) -> bool:
        return bool(
            wait_for(lambda: Session(self.a.base).call("GET", "/healthz", timeout=3)[0] == 200,
                     timeout, 2)
        )

    def accepts_alerts_again(self, label: str) -> None:
        status, body = self.trigger(f"after {label}", key=f"drill-{label.replace(' ', '-')}")
        check(f"{label}: alerts are accepted again", status == 202, f"{status}")
        if status == 202:
            self.api.call("POST", f"/api/v1/incidents/{body['incident_id']}/resolve/")

    def drill_api_crash(self) -> None:
        # `docker kill` / `compose kill` count as a manual stop, which restart policies
        # deliberately respect. A real crash is the process dying on its own, so simulate that.
        say("drill 4a: every gunicorn worker is SIGKILLed")
        killer = (
            "import os, signal\n"
            "for p in filter(str.isdigit, os.listdir('/proc')):\n"
            "    try:\n"
            "        stat = open(f'/proc/{p}/stat').read().rsplit(')', 1)[1].split()\n"
            "        if stat[1] == '1' and b'gunicorn' in open(f'/proc/{p}/cmdline','rb').read():\n"
            "            os.kill(int(p), signal.SIGKILL)\n"
            "    except OSError:\n"
            "        pass\n"
        )
        self.dc("exec", "-T", self.a.api_service, "python", "-c", killer)
        time.sleep(1)
        check("workers killed: gunicorn's master respawns them", self.api_up(60))
        self.accepts_alerts_again("worker crash")

        say("drill 4b: the API process exits on its own (container crash)")
        before = self.restart_count()
        self.dc("exec", "-T", self.a.api_service, "python", "-c",
                "import os, signal; os.kill(1, signal.SIGTERM)")
        ok = wait_for(lambda: (self.restart_count() or 0) > (before or 0), 60, 2)
        check("container exited by itself: the restart policy restarts it", bool(ok),
              f"restart count {before} -> {self.restart_count()}")
        check("container restarted: healthy again, migrations re-run harmlessly", self.api_up(120))
        check("container restarted: /readyz ok",
              bool(wait_for(lambda: self.ready()[0] == 200, 60, 2)))
        self.accepts_alerts_again("container restart")

    def restart_count(self) -> int | None:
        proc = subprocess.run([*self.compose, "ps", "-q", self.a.api_service],
                              capture_output=True, text=True, check=False)
        cid = proc.stdout.strip().splitlines()[:1]
        if not cid:
            return None
        out = subprocess.run(["docker", "inspect", "-f", "{{.RestartCount}}", cid[0]],
                             capture_output=True, text=True, check=False)
        return int(out.stdout.strip()) if out.stdout.strip().isdigit() else None

    # --- run ---------------------------------------------------------------------------
    STEPS = ("basics", "flow", "redis", "worker", "db", "api", "throttle")

    def run(self) -> int:
        say(f"doctor against {self.a.base} (mail {self.a.mail})")
        only = set(self.a.only.split(",")) if self.a.only else set(self.STEPS)
        if self.a.skip_drills:
            only -= {"redis", "worker", "db", "api"}
        if "basics" in only:
            self.basics()
        if only - {"basics"} and self.sign_in():
            if "flow" in only:
                self.alert_flow()
            for name, fn in (("redis", self.drill_redis), ("worker", self.drill_worker),
                             ("db", self.drill_db), ("api", self.drill_api_crash)):
                if name in only:
                    fn()
            if "throttle" in only:
                self.throttle_spoof()  # last: it deliberately trips the login throttle
        failed = [r for r in RESULTS if not r[1]]
        print("\n" + "=" * 72)
        for name, ok, detail in RESULTS:
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
        print("=" * 72)
        print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed in {time.time() - T0:.0f}s")
        return 1 if failed else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--compose", default="docker compose -f docker-compose.prod.yml")
    p.add_argument("--api-service", default="api")
    p.add_argument("--base", default="http://localhost:8080")
    p.add_argument("--mail", default="http://localhost:8025")
    p.add_argument("--skip-drills", action="store_true")
    p.add_argument("--only", help="comma list of: basics,flow,redis,worker,db,api,throttle")
    return Doctor(p.parse_args()).run()


if __name__ == "__main__":
    sys.exit(main())
