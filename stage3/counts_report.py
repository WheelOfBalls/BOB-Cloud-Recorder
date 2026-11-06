#!/usr/bin/env python3
# Counts-only report on stage 3 recordings (the pilot, or coverage during the live recording).
# It prints counts, shares and timings only: no index level, no quote, mid, p_opt, gap, outcome or trade.
# The one price-derived figure is the spread histogram (ask - bid, in cents) on hourly rows, which DESIGN.md
# ("Before the start", step 2) asks the pilot for. It is printed only when every snapshot is a pilot or test
# snapshot, never on live data (the pre-registration allows only counts while recording).
#
#   python3 -I stage3/counts_report.py --data <checkout>/data [--out report.md] [--json report.json]
import os, sys, json, gzip, glob, argparse, statistics, collections, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import record_snapshot as rs  # noqa: E402

UTC = dt.timezone.utc
STEP, PHASE = 300, 150
SLOTS_PER_DAY = 288
NEED_FRAC = 0.80
MID_LO, MID_HI = 0.06, 0.94
MIN_TO_CLOSE = (2.0, 60.0)


def iso_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def q(xs, ps=(0.5, 0.9, 0.99, 1.0)):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return "n/a"
    return " / ".join(f"{xs[min(len(xs) - 1, int(p * (len(xs) - 1) + 0.5))]:.2f}" for p in ps)


def slot_of(t):
    return int(round((t - PHASE) / STEP))


def slot_t(i):
    return i * STEP + PHASE


def day(t):
    return dt.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d")


def hm(t):
    return dt.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d %H:%M")


def load(data):
    snaps = []
    bad = []
    for p in sorted(glob.glob(os.path.join(data, "*", "*.json.gz"))):
        try:
            with gzip.open(p, "rt") as f:
                s = json.load(f)
            s["_bytes"] = os.path.getsize(p)
            s["_t"] = iso_ts(s["utc"])
            snaps.append(s)
        except Exception:
            bad.append(p)
    snaps.sort(key=lambda s: s["_t"])
    return snaps, bad


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        lines = [ln.rstrip("\n").split(",") for ln in f if ln.strip()]
    if not lines:
        return []
    head = lines[0]
    return [dict(zip(head, ln)) for ln in lines[1:] if ln != head]


def report(data, allow_spreads=None):
    snaps, bad = load(data)
    modes = collections.Counter(s.get("mode") for s in snaps)
    if allow_spreads is None:
        allow_spreads = bool(snaps) and set(modes) <= {"pilot", "test", "manual"}
    out = {"generated_utc": dt.datetime.now(UTC).isoformat(timespec="seconds"), "snapshots": len(snaps),
           "unreadable": len(bad), "modes": dict(modes)}
    L = [f"# Stage 3 counts-only report", "", f"Generated {out['generated_utc']}. Data: `{data}`. "
         "Counts, shares and timings only; no prices, gaps, p_opt or outcomes.", ""]
    if not snaps:
        L.append("No snapshots.")
        return "\n".join(L) + "\n", out
    first, last = snaps[0]["_t"], snaps[-1]["_t"]
    L.append(f"Snapshots: {len(snaps)} ({hm(first)} to {hm(last)} UTC), unreadable {len(bad)}, modes {dict(modes)}.")
    L.append("")

    # ---- slots and validity ----
    by_slot = collections.defaultdict(list)
    for s in snaps:
        tgt = (s.get("source") or {}).get("slot_target")
        t = iso_ts(tgt) if tgt else s["_t"]
        by_slot[slot_of(t)].append(s)
    first_slot, last_slot = min(by_slot), max(by_slot)
    days = collections.defaultdict(lambda: {"slots": 0, "recorded": 0, "btc": 0, "eth": 0, "both": 0})
    for i in range(first_slot, last_slot + 1):
        d = days[day(slot_t(i))]
        d["slots"] += 1
        if i in by_slot:
            s = by_slot[i][0]                    # the first snapshot in a slot counts, as stage 2
            d["recorded"] += 1
            vb, _ = rs.validity(s, "BTC")
            ve, _ = rs.validity(s, "ETH")
            d["btc"] += vb; d["eth"] += ve; d["both"] += vb and ve
    dup = sum(len(v) - 1 for v in by_slot.values())
    L += ["## Slots and validity (per UTC day)", "",
          "A day counts in the live test if at least 80% of its 288 slots are valid for both coins. "
          "Partial days here are the pilot's edges.", "",
          "| Day | Slots in span | Recorded | Valid BTC | Valid ETH | Valid both | Share of 288 valid both | Would count |",
          "|---|---|---|---|---|---|---|---|"]
    for k in sorted(days):
        d = days[k]
        L.append(f"| {k} | {d['slots']} | {d['recorded']} | {d['btc']} | {d['eth']} | {d['both']} | "
                 f"{d['both'] / SLOTS_PER_DAY:.0%} | {'yes' if d['both'] >= NEED_FRAC * SLOTS_PER_DAY else 'no'} |")
    L += ["", f"Duplicate snapshots in a slot: {dup}.", ""]
    out["days"] = dict(days)

    # ---- timing ----
    late, dur, size, nbooks, trunc = [], [], [], [], 0
    gap = {"BTC": [], "ETH": []}
    pull = {"BTC": [], "ETH": []}
    span = {"BTC": [], "ETH": []}
    chain_s = {"BTC": [], "ETH": []}
    pages = collections.Counter()
    for s in snaps:
        tgt = (s.get("source") or {}).get("slot_target")
        if tgt:
            late.append(s["_t"] - iso_ts(tgt))
        if s.get("t_end"):
            dur.append(s["t_end"] - s["_t"])
        size.append(s["_bytes"] / 1024)
        nbooks.append(len(s.get("books") or {}))
        trunc += bool(s.get("books_truncated"))
        for c in ("BTC", "ETH"):
            cc = s["coins"].get(c) or {}
            ch, kd, i0, i1 = cc.get("chain") or {}, cc.get("kalshi") or {}, cc.get("index_before") or {}, cc.get("index_after") or {}
            if ch.get("t1") and kd.get("t1"):
                gap[c].append(abs(kd["t1"] - ch["t1"]))
                chain_s[c].append(ch["t1"] - ch["t0"])
                pull[c].append(kd["t1"] - kd["t0"])
                pages[(c, kd.get("pages"))] += 1
            if i0.get("t0") and i1.get("t1"):
                span[c].append(i1["t1"] - i0["t0"])
    L += ["## Timing (seconds; median / 90% / 99% / max)", "",
          f"- Snapshot start after its slot target: {q(late)}",
          f"- Snapshot duration (start to end of the last request): {q(dur)}"]
    for c in ("BTC", "ETH"):
        L += [f"- {c}: Deribit chain request {q(chain_s[c])}; Kalshi market list {q(pull[c])}; "
              f"|Kalshi list end - chain end| {q(gap[c])} (validity needs <= 5); index_before start to index_after end {q(span[c])}"]
    L += [f"- Kalshi list pages per snapshot: {dict((f'{c} {p}', n) for (c, p), n in sorted(pages.items(), key=str))}",
          f"- Order books per snapshot: {q(nbooks)}; snapshots where the book budget ran out: {trunc}",
          f"- Snapshot size (KB, gzipped): {q(size)}; total {sum(size) / 1024:.1f} MB", ""]
    out["timing"] = {"late": q(late), "duration": q(dur), "books": q(nbooks), "kb": q(size), "books_truncated": trunc}

    # ---- event schedule (hourly events) ----
    ev = {}
    for s in snaps:
        for c in ("BTC", "ETH"):
            kd = (s["coins"].get(c) or {}).get("kalshi") or {}
            per = collections.defaultdict(list)
            for m in kd.get("markets") or []:
                per[m.get("event_ticker") or ""].append(m)
            for e, ms in per.items():
                close = next((iso_ts(m["close_time"]) for m in ms if m.get("close_time")), None)
                if close is None:
                    continue
                r = ev.setdefault(e, {"coin": c, "close": close, "hourly": rs.is_hourly(e), "seen": [], "n": [], "spacing": set(),
                                      "opens": set()})
                r["seen"].append((close - s["_t"]) / 60)
                r["n"].append(len(ms))
                ks = sorted({fnum(m.get("floor_strike")) for m in ms if fnum(m.get("floor_strike")) is not None})
                r["spacing"] |= {round(b - a, 2) for a, b in zip(ks, ks[1:])}
                r["opens"] |= {m.get("open_time") for m in ms if m.get("open_time")}
    hourly = {e: r for e, r in ev.items() if r["hourly"]}
    L += ["## Kalshi event schedule", "",
          f"Distinct events seen: {len(ev)} ({len(hourly)} hourly, {len(ev) - len(hourly)} ending in 17).", ""]
    for c in ("BTC", "ETH"):
        hs = sorted((r for r in hourly.values() if r["coin"] == c), key=lambda r: r["close"])
        closes = {r["close"] for r in hs}
        lo_h = int(first // 3600 + 1) * 3600
        hi_h = int(last // 3600) * 3600
        expected = list(range(lo_h, hi_h + 1, 3600))
        missing = [t for t in expected if t not in closes]
        # 17:00 ET closes are the daily events; they are not hourly events, so they are expected to be missing
        missing_not_daily = [t for t in missing if not any(abs(r["close"] - t) < 1 for r in ev.values()
                                                            if r["coin"] == c and not r["hourly"])]
        first_seen = [max(r["seen"]) for r in hs]
        L += [f"**{c}.** Hourly events seen: {len(hs)}. Whole hours in span: {len(expected)}; hours with no hourly event: "
              f"{len(missing)} (of which not a 5pm ET close: {len(missing_not_daily)}"
              + (f": {', '.join(hm(t) for t in missing_not_daily[:12])}" if missing_not_daily else "") + ").",
              f"Minutes before close an hourly event was first listed (median / 90% / 99% / max): {q(first_seen)}; "
              f"markets per hourly event per snapshot: {q([x for r in hs for x in r['n']])}; "
              f"strike spacings seen: {sorted(set().union(*[r['spacing'] for r in hs])) [:6] if hs else []}.", ""]
        out[f"events_{c}"] = {"hourly": len(hs), "hours": len(expected), "missing": len(missing),
                              "missing_not_daily": [hm(t) for t in missing_not_daily]}
    hourly_open = collections.Counter()
    for s in snaps:
        for c in ("BTC", "ETH"):
            kd = (s["coins"].get(c) or {}).get("kalshi") or {}
            hourly_open[(c, len({m.get("event_ticker") for m in kd.get("markets") or [] if rs.is_hourly(m.get("event_ticker"))}))] += 1
    L += [f"Open hourly events per snapshot (coin, count: snapshots): {dict((f'{c} {n}', k) for (c, n), k in sorted(hourly_open.items()))}", ""]

    # ---- rows (counts only) ----
    rows = collections.Counter()
    spreads = collections.Counter()
    buckets = collections.Counter()
    per_snap = []
    for s in snaps:
        n = 0
        for c in ("BTC", "ETH"):
            if not rs.validity(s, c)[0]:
                continue
            kd = s["coins"][c]["kalshi"]
            for m in kd["markets"]:
                if not rs.is_hourly(m.get("event_ticker")) or not m.get("close_time"):
                    continue
                b, a = fnum(m.get("yes_bid_dollars")), fnum(m.get("yes_ask_dollars"))
                if b is None or a is None or not (0 < b < a < 1):
                    continue
                mins = (iso_ts(m["close_time"]) - kd["t1"]) / 60
                if not (MIN_TO_CLOSE[0] <= mins <= MIN_TO_CLOSE[1]) or not (MID_LO - 1e-9 <= (a + b) / 2 <= MID_HI + 1e-9):
                    continue
                n += 1
                rows[c] += 1
                buckets["2-15" if mins < 15 else "15-30" if mins < 30 else "30-60"] += 1
                if allow_spreads:
                    t = int(round((a - b) * 100))
                    spreads[str(t) if t <= 5 else "6-10" if t <= 10 else ">10"] += 1
        per_snap.append(n)
    L += ["## Candidate rows (counts only)", "",
          "Valid snapshot x hourly market with a two-sided quote, mid in [0.06, 0.94] and 2 to 60 minutes to close.", "",
          f"- Rows: BTC {rows['BTC']}, ETH {rows['ETH']}; per snapshot {q(per_snap)}",
          f"- By minutes to close: {dict(buckets)}"]
    if allow_spreads:
        tot = sum(spreads.values()) or 1
        order = ["1", "2", "3", "4", "5", "6-10", ">10"]
        L.append("- Spread (ask - bid, cents) on those rows: " + ", ".join(f"{k}: {spreads[k]} ({spreads[k] / tot:.0%})" for k in order))
        out["spreads"] = {k: spreads[k] for k in order}
    else:
        L.append("- Spread histogram: not shown on live data.")
    L.append("")
    out["rows"] = dict(rows)

    # ---- Deribit chains (counts only) ----
    L += ["## Deribit chains", ""]
    for c in ("BTC", "ETH"):
        n_opt, fit_ok = [], collections.Counter()
        for s in snaps:
            opts = ((s["coins"].get(c) or {}).get("chain") or {}).get("options") or []
            n_opt.append(len(opts))
            per = collections.Counter()
            for o in opts:
                b, a, F, iv = fnum(o.get("bid_price")), fnum(o.get("ask_price")), fnum(o.get("underlying_price")), fnum(o.get("mark_iv"))
                try:
                    _, _, k, cp = o["instrument_name"].split("-")
                    k = float(k)
                except (ValueError, KeyError):
                    continue
                if None in (b, a, F, iv) or b <= 0 or a < b:
                    continue
                if (k >= F) == (cp == "C"):
                    per[o["instrument_name"].split("-")[1]] += 1
            fit_ok[sum(1 for v in per.values() if v >= 4)] += 1
        L.append(f"- {c}: options within 3 days per snapshot {q(n_opt)}; expiries with >= 4 two-sided OTM options with mark_iv "
                 f"(expiries: snapshots) {dict(sorted(fit_ok.items()))}")
    L.append("")

    # ---- 1-minute index polls ----
    L += ["## 1-minute index polls", ""]
    polls = []
    for p in sorted(glob.glob(os.path.join(data, "index_1m", "*.csv"))):
        polls += read_csv(p)
    if polls:
        tg = sorted({iso_ts(r["target_utc"]) for r in polls})
        lo, hi = tg[0], tg[-1]
        exp = int((hi - lo) // 60) + 1
        for c in ("BTC", "ETH"):
            ok = {iso_ts(r["target_utc"]): r for r in polls if r["coin"] == c and r.get("index_price")}
            lat = [float(r["t0"]) - iso_ts(r["target_utc"]) for r in ok.values()]
            dur_ = [float(r["t1"]) - float(r["t0"]) for r in ok.values()]
            closes = [t for t in range(int(lo // 3600 + 1) * 3600, int(hi) + 1, 3600)]
            at_close = sum(1 for t in closes if t in ok and float(ok[t]["t0"]) - t < 5)
            L.append(f"- {c}: minutes in span {exp}, with a price {len(ok)} ({len(ok) / exp:.1%}), missing {exp - len(ok)}; "
                     f"start after the minute {q(lat)} s; request {q(dur_)} s; whole hours polled within 5 s: {at_close}/{len(closes)}")
            out[f"index_{c}"] = {"minutes": exp, "ok": len(ok)}
    else:
        L.append("- none")
    L.append("")

    # ---- errors, loop log, series ----
    err = collections.Counter()
    for s in snaps:
        for e in s.get("errors") or []:
            err[e.split(":")[0]] += 1
    loop = read_csv(os.path.join(data, "cloud_loop.csv"))
    runs = [r for r in loop if r.get("kind") == "run_start"]
    slots = [r for r in loop if r.get("kind") == "slot"]
    failed_push = sum(1 for r in slots if "push failed" in r.get("status", ""))
    rc_bad = sum(1 for r in slots if not r.get("status", "").startswith("rc=0"))
    crash = os.path.join(data, "crash_log.txt")
    hang = os.path.join(data, "hang_log.txt")
    L += ["## Errors and runs", "",
          f"- Request errors by endpoint: {dict(err.most_common(10)) or 'none'}",
          f"- Runs started: {len(runs)}; slot attempts {len(slots)}; non-zero exit {rc_bad}; failed pushes {failed_push}",
          f"- crash_log bytes: {os.path.getsize(crash) if os.path.exists(crash) else 0}; "
          f"hang_log bytes: {os.path.getsize(hang) if os.path.exists(hang) else 0}"]
    meta = read_csv(os.path.join(data, "series_meta.csv"))
    if meta:
        seen = sorted({(r["series"], r["frequency"], r["fee_type"], r["fee_multiplier"]) for r in meta})
        L.append(f"- Series fee fields seen (series, frequency, fee_type, fee_multiplier): {seen}")
    L.append("")
    out["errors"] = dict(err)
    return "\n".join(L) + "\n", out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out")
    ap.add_argument("--json")
    ap.add_argument("--no-spreads", action="store_true")
    a = ap.parse_args()
    text, js = report(a.data, allow_spreads=False if a.no_spreads else None)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w") as f:
            f.write(text)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(js, f, indent=1, default=str)
    print(text)


if __name__ == "__main__":
    main()
