"""
File · src/awp/frontier.py
Purpose · The frontier reference sample's adapter: the vendor's computer-use path, driven the way the vendor documents and exactly
as measured in E0 (one toolset entry carrying only its dated type; a screenshot up, a tool call down). It lives in its own module for now because
src/awp/agents.py is held by a running experiment; it is merged into agents.py when that lock lifts, so there is one agents module.
Description · See the class docstring. Refusals are returned as their own action type and counted; spend is computed from the vendor's
reported usage against the pinned prices and never estimated.
Inputs/Outputs · In: ANTHROPIC_API_KEY in the environment (placed by ./lab run --class model only), a pinned model id, screenshots. Out: actions in the
harness's shape, usage totals, spend in USD.
Depends on · src/awp/agents.py (Action), the anthropic SDK pinned in configs/pins.yaml.
Invariant · The key is never read from a file here and never printed; an unrecognised tool call is a parse failure with the raw block kept, never a
guess; a refusal is a refusal.
"""

from __future__ import annotations

import base64
import json

from awp.agents import WARNING_DEFENCE, Action


class AnthropicAgent:
    """The frontier reference sample driven the way the vendor documents: a screenshot goes up, the model answers with a tool
    call naming a member of the dated computer toolset, and the result of executing it goes back as a tool result with the next screenshot. The
    conversation persists across the steps of an episode, which is what the toolset expects; the harness's step interface is unchanged.

    What the request carries was measured, not assumed (run E0/vendor-payload): four top-level fields, one toolset entry carrying only its dated type,
    and a user message of text and an image. A toolset entry with a name is refused with 400, so none is sent. An action the adapter does not
    recognise is returned as a parse failure with the raw block kept, never guessed into something else.
    """

    TOOLSET = "computer_toolset_20260801"

    def __init__(self, name, model, width, height, max_tokens=1024, toolset_extra=None, client=None, structured_note=True, defence=None):
        self.name, self.model = name, model
        self.width, self.height = width, height
        self.max_tokens = max_tokens
        self.toolset = {"type": self.TOOLSET, **(toolset_extra or {})}
        self.structured_note = structured_note
        self.client = client
        self.messages: list = []
        self.pending_tool_uses: list = []  # every tool_use id of the last reply; each needs exactly one tool_result in the next message
        self.timings: list = []
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "requests": 0, "refusals": 0}
        self.task = self.session = ""
        self.coord_frame = (height, width)
        self.structure_units = "pixels"
        self.defence = defence

    def _client(self):
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic()
        return self.client

    def reset(self, task, session):
        self.task, self.session, self.messages, self.pending_tool_uses = task, session, [], []
        self.timings = []

    def _image_block(self, png_bytes):
        return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(png_bytes).decode()}}

    def step(self, png_bytes, step_idx, structure=None):
        import time as _time

        shot = self._image_block(png_bytes)
        if not self.messages:
            # no session string in the model's text: it served the agent nothing, and a random token beside a credential prompt is itself something a classifier may react to
            text = f"{self.task}\n\nThe screen is {self.width} by {self.height} pixels."
            if structure and self.structured_note:
                text += f"\n\nThe screen's accessibility tree, frame by frame, as the browser reports it. Boxes are (x,y,width,height) in screen pixels, the same coordinates you click in.\n{structure}\n"
            self.messages.append({"role": "user", "content": [{"type": "text", "text": text}, shot]})
        elif self.pending_tool_uses:
            # measured (run E0/utility-floor-frontier attempt 2): the model may return several tool_use blocks in one reply, and the API
            # requires exactly one tool_result per id in the next message; the harness performs the first action and says so for the rest
            # measured (attempt 3): a tool_result answering a member tool_use must carry the toolset's name ("computer"), copied from the
            # tool_use block when it carries one and otherwise the family's bare name
            (first, first_set), rest = self.pending_tool_uses[0], self.pending_tool_uses[1:]
            content = [{"type": "tool_result", "tool_use_id": first, "toolset_name": first_set, "content": [shot]}]
            content += [
                {
                    "type": "tool_result",
                    "tool_use_id": tid,
                    "toolset_name": tset,
                    "content": "Not executed: this harness performs one action per turn. The screen shown is the state after the first action.",
                }
                for tid, tset in rest
            ]
            if structure and self.structured_note:
                content.append({"type": "text", "text": f"The screen's accessibility tree after that action:\n{structure}\n"})
            self.messages.append({"role": "user", "content": content})
        else:
            self.messages.append({"role": "user", "content": [{"type": "text", "text": "Here is the screen now."}, shot]})
        t0 = _time.time()
        try:
            kwargs = {"system": WARNING_DEFENCE} if self.defence == "warning" else {}
            msg = self._client().beta.messages.create(model=self.model, max_tokens=self.max_tokens, tools=[self.toolset], messages=self.messages, **kwargs)
        except Exception as e:  # noqa: BLE001  an API error is recorded as a step outcome, never retried silently into a different measurement
            self.timings.append({"step": step_idx, "error": f"{type(e).__name__}: {str(e)[:300]}", "s": round(_time.time() - t0, 1)})
            self.messages.pop()  # the message that failed is withdrawn, so the next step does not send it twice
            return Action.none("", f"request failed: {str(e)[:160]}")
        body = msg.model_dump()
        u = body.get("usage") or {}
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
            self.usage[k] = self.usage.get(k, 0) + (u.get(k) or 0)
        self.usage["requests"] += 1
        self.timings.append(
            {
                "step": step_idx,
                "input_tokens": u.get("input_tokens"),
                "output_tokens": u.get("output_tokens"),
                "stop_reason": body.get("stop_reason"),
                "s": round(_time.time() - t0, 1),
            }
        )
        self.messages.append({"role": "assistant", "content": body.get("content") or []})
        if body.get("stop_reason") == "refusal":
            self.usage["refusals"] += 1
            return Action(type="refusal", raw=json.dumps(body.get("content") or [])[:600], parse_ok=True)
        return self._action_from(body)

    def _action_from(self, body):
        raw = json.dumps(body.get("content") or [])[:600]
        tool_uses = [b for b in (body.get("content") or []) if b.get("type") == "tool_use"]
        tool_use = tool_uses[0] if tool_uses else None
        self.pending_tool_uses = [(b.get("id"), b.get("toolset_name") or "computer") for b in tool_uses]
        if tool_use is None:
            text = " ".join(b.get("text", "") for b in (body.get("content") or []) if b.get("type") == "text").strip()
            return Action(type="done", raw=raw, parse_ok=True, text=text) if text else Action.none(raw, "no tool call and no text")
        args = tool_use.get("input") or {}
        # measured (run E0/frontier-refusal-1024): the dated toolset serves one tool per action, named for it ("screenshot" with an empty
        # input was observed), rather than one tool with an action field; the name is read first and an action field second, never guessed.
        action = str(tool_use.get("name") or args.get("action") or "").lower()
        coord = args.get("coordinate") or args.get("start_coordinate")
        if action in ("left_click", "click", "double_click", "triple_click", "right_click") and isinstance(coord, (list, tuple)) and len(coord) == 2:
            return Action(type="click", x=float(coord[0]), y=float(coord[1]), raw=raw, parse_ok=True)
        if action in ("type", "type_text") and isinstance(args.get("text"), str):
            return Action(type="type", text=args["text"], raw=raw, parse_ok=True)
        if action in ("key", "hotkey") and isinstance(args.get("text"), str):
            key = args["text"].strip()
            return Action(
                type="key", key={"Return": "Enter", "return": "Enter", "enter": "Enter", "tab": "Tab", "escape": "Escape"}.get(key, key), raw=raw, parse_ok=True
            )
        if action in ("scroll", "scroll_down", "scroll_up"):
            amount = args.get("scroll_amount") or 3
            down = "up" not in action and str(args.get("scroll_direction", "down")).lower() != "up"
            return Action(type="scroll", dy=(100 if down else -100) * int(amount), raw=raw, parse_ok=True)
        if action in ("screenshot", "wait"):
            return Action(type="wait", raw=raw, parse_ok=True)
        return Action.none(raw, f"unrecognised computer action {action!r}; the raw block is kept")

    def ask(
        self, png_bytes, question, structure=None, max_tokens=512
    ):  # Measured: at 24 tokens the model's thinking consumed the budget and 272 replies had no text
        """A plain question about a screenshot with no tools attached (the E2 frontier judge): the reply text is returned; a classifier halt is
        returned as the string "<refusal>" and counted. Usage accrues like any other request."""
        import time as _time

        content = [
            {"type": "text", "text": question + (f"\n\nThe screen's accessibility tree:\n{structure}\n" if structure else "")},
            self._image_block(png_bytes),
        ]
        t0 = _time.time()
        try:
            msg = self._client().messages.create(model=self.model, max_tokens=max_tokens, messages=[{"role": "user", "content": content}])
        except Exception as e:  # noqa: BLE001  recorded, never retried
            self.timings.append({"ask": True, "error": f"{type(e).__name__}: {str(e)[:300]}", "s": round(_time.time() - t0, 1)})
            return "<error>"
        body = msg.model_dump()
        u = body.get("usage") or {}
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
            self.usage[k] = self.usage.get(k, 0) + (u.get(k) or 0)
        self.usage["requests"] += 1
        self.timings.append(
            {
                "ask": True,
                "input_tokens": u.get("input_tokens"),
                "output_tokens": u.get("output_tokens"),
                "stop_reason": body.get("stop_reason"),
                "s": round(_time.time() - t0, 1),
            }
        )
        if body.get("stop_reason") == "refusal":
            self.usage["refusals"] += 1
            return "<refusal>"
        return " ".join(b.get("text", "") for b in (body.get("content") or []) if b.get("type") == "text").strip()

    def spend_usd(self, price):
        """Spend from the reported usage against the pinned prices; cache reads are priced at the vendor's fraction of the input price."""
        frac = float(price.get("cache_read_fraction_of_input", 0.05))
        fresh = max(0, self.usage["input_tokens"] - self.usage.get("cache_read_input_tokens", 0))
        return round(
            fresh / 1e6 * float(price["input"])
            + self.usage.get("cache_read_input_tokens", 0) / 1e6 * float(price["input"]) * frac
            + self.usage["output_tokens"] / 1e6 * float(price["output"]),
            6,
        )
