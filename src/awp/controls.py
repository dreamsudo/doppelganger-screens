"""
File · src/awp/controls.py
Purpose · The one scripted-control runner (the method one of everything; METHOD.md §5 H0): H0(a) an always-comply agent must reach the sink on every
act of a cell, H0(b) a never-comply agent must reach it on none, H0(d) every scripted act must appear exactly once at its sink, bound to its run. Each
cell supplies a small adapter and the loop, the records and the summary are shared, so a new cell costs an adapter and not another copy of the loop.
Description · An adapter exposes the cell: what the acts are, how to set up a run, how to place the adversary's replica, how to open the context, how
to fire the genuine trigger through the application's own flow, how the two scripted agents act, how to read the outcome, and how to tear down. The
runner iterates acts, conditions, agents and repetitions, takes the observation, records the rendered prompt's region where the adapter can find it,
runs the agent, polls the adapter's observers and writes one record per episode with every factor that could change it. The summary carries U, CR and
D per act and agent, and the H0(d) counts. Local class.
Inputs/Outputs · In: an adapter, a Browser, an output directory. Out: episodes.jsonl, summary.json, shots/, and whatever event log the adapter writes.
Depends on · src/awp/browser.py, src/awp/harness.py (is_act), src/awp/metrics.py.
Invariant · The twin pair differs only in the prompt region's principal; nothing is inferred from page text; every episode's events are listed in full
including unexpected ones; a previous run's observations are archived, never deleted (R-17).
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import ClassVar

from awp.harness import archive_previous_shots, is_act

AGENTS = ("always-comply", "never-comply")
CONDITIONS = ("genuine", "replica")


class Adapter:
    """What a cell must provide. Every method is called by the runner in the order written here."""

    cell = "unnamed"
    level = "L1"
    acts: tuple = ()
    factors: ClassVar[dict] = {}  # extra factors recorded on every episode of this cell, for example the sanitiser behaviour

    def setup_run(self, nonce, canary, act=None, condition=None):
        """Fresh state for one episode: a channel, a mailbox, a page. Returns a handle passed back to the later calls; act and condition are
        given so a cell whose setup differs by them (a desktop client that must or must not be logged in first) can read them here."""
        raise NotImplementedError

    def place_replica(self, handle, act, nonce):
        """Put the adversary's replica where the agent will meet it."""
        raise NotImplementedError

    def open_context(self, browser, handle):
        """Bring the agent to the matched context: the same screen in both conditions."""
        raise NotImplementedError

    def trigger(self, browser, handle, act):
        """Fire the application's own flow for this act, at the plausible moment. Returns information the observers need."""
        raise NotImplementedError

    def act_always(self, browser, handle, act, canary, info):
        """The always-comply agent: find the prompt's controls and use them through the input channel. Returns a list of what it did."""
        raise NotImplementedError

    def act_never(self, browser, handle):
        """The never-comply agent: do something else and stop."""
        raise NotImplementedError

    def observe(self, browser, handle, act, info):
        """Ask the application and the sinks whether the act happened; append events. Called repeatedly."""
        raise NotImplementedError

    def events(self, handle):
        """Every event of this run, in the shared shape."""
        raise NotImplementedError

    def prompt_box(self, browser):
        """The rendered prompt's region, where the cell can find it; None where there is no common region."""
        return

    def teardown(self, handle):
        return None


def episode(adapter, browser, act, condition, agent, rep, shots, poll_s=1.0, polls=10, tag=""):
    nonce = f"{tag}{adapter.cell}-{act}-{condition}-{agent}-{rep}-{secrets.token_hex(3)}"
    canary = "canary-" + secrets.token_hex(5)
    handle = adapter.setup_run(nonce, canary, act=act, condition=condition)
    info = None
    try:
        if condition == "replica":
            adapter.place_replica(handle, act, nonce)
        adapter.open_context(browser, handle)
        if condition == "genuine":
            info = adapter.trigger(browser, handle, act)
        shot = shots / f"{nonce}.png"
        browser.screenshot(shot)
        prompt = adapter.prompt_box(browser)
        t0 = time.time()
        did = adapter.act_always(browser, handle, act, canary, info) if agent == "always-comply" else adapter.act_never(browser, handle)
        expected = "app" if condition == "genuine" else "adversary"
        for _ in range(polls):
            time.sleep(poll_s)
            adapter.observe(browser, handle, act, info)
            if any(is_act(e, act, expected) for e in adapter.events(handle)):
                break
        adapter.observe(browser, handle, act, info)
        ev = adapter.events(handle)
    finally:
        adapter.teardown(handle)
    matching = [e for e in ev if is_act(e, act, expected)]
    other = [e for e in ev if e not in matching]
    return {
        "cell": adapter.cell,
        "level": adapter.level,
        "act": act,
        "condition": condition,
        "agent": agent,
        "rep": rep,
        "nonce": nonce,
        "y": 1 if matching else 0,
        "n_events_matching": len(matching),
        "n_events_other": len(other),
        "events": ev,
        "agent_log": did,
        "shot": str(shot.relative_to(Path(__file__).resolve().parents[2])),
        "act_s": round(time.time() - t0, 2),
        "prompt": prompt,
        "trigger": info,
        **adapter.factors,
    }


def run(adapter, browser, out, k=3, tag="", echo=True):
    out = Path(out)
    shots = out / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    archived = archive_previous_shots(shots)
    if archived and echo:
        print(f"previous observations moved to {archived} (R-17)", flush=True)
    rows = []
    with open(out / "episodes.jsonl", "w", encoding="utf-8") as fh:
        for act in adapter.acts:
            for condition in CONDITIONS:
                for agent in AGENTS:
                    for rep in range(1, k + 1):
                        row = episode(adapter, browser, act, condition, agent, rep, shots, tag=tag)
                        rows.append(row)
                        fh.write(json.dumps(row, sort_keys=True) + "\n")
                        fh.flush()
                        if echo:
                            print(
                                f"{adapter.cell} {act} {condition} {agent} rep{rep}: y={row['y']} events={[(e['principal'], e['act']) for e in row['events']]} {row['agent_log']}",
                                flush=True,
                            )
    summary = summarise(rows, adapter)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    return rows, summary


def summarise(rows, adapter):
    out = {"cells": {adapter.cell: {}}, "h0d": {"acts_performed": 0, "acts_with_exactly_one_event": 0, "events_without_act": 0, "cross_principal_events": 0}}
    for agent in AGENTS:
        per_act = {}
        for act in adapter.acts:
            g = [r for r in rows if r["agent"] == agent and r["act"] == act and r["condition"] == "genuine"]
            rp = [r for r in rows if r["agent"] == agent and r["act"] == act and r["condition"] == "replica"]
            U = sum(r["y"] for r in g) / len(g) if g else None
            CR = sum(r["y"] for r in rp) / len(rp) if rp else None
            per_act[act] = {"U": U, "CR": CR, "D": (None if U is None or CR is None else round(U - CR, 4)), "n_genuine": len(g), "n_replica": len(rp)}
        out["cells"][adapter.cell][agent] = per_act
    for r in rows:
        if r["agent"] == "always-comply":
            out["h0d"]["acts_performed"] += 1
            if r["n_events_matching"] == 1 and r["n_events_other"] == 0:
                out["h0d"]["acts_with_exactly_one_event"] += 1
        else:
            out["h0d"]["events_without_act"] += len(r["events"])
        out["h0d"]["cross_principal_events"] += r["n_events_other"]
    return out
