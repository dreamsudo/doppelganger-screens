"""
File · src/awp/browser.py
Purpose · The one browser driver for the browser cells: a Chromium page with a fixed 1280x832 viewport, screenshots as the pixels-only observation, clicks and typing through the input channel (never through the DOM), and element location through the accessibility tree for the scripted control agents, in the main frame and inside cross-origin frames.
Description · Builds on awp.cdp.CDP (DevTools pipe). open() creates a page, pins the viewport with Emulation.setDeviceMetricsOverride, and auto-attaches child targets so an out-of-process iframe (the L2 content region) gets its own session. find() walks the accessibility tree of the main frame and of every attached child frame, matches role and name, resolves the node's box with DOM.getBoxModel, and adds the frame's offset in the page so the returned point is in screenshot pixels. click() and type_text() send Input.dispatchMouseEvent and Input.insertText to the page session; Chromium routes them to whichever frame is under the point, exactly as a user's pointer would be. Shaped on 2026-10-19 by the lab app (awp.labapp) and the pilot's browser_levels.py.
Inputs/Outputs · In: a deadline, a start URL. Out: PNG bytes, accessibility matches with page coordinates, frame lists. No network beyond what the page requests.
Depends on · src/awp/cdp.py, src/awp/proc.py, chromium.
Invariant · Actions go through the input channel only; the viewport is fixed so screenshot pixels equal page CSS pixels; every page is closed by close().
"""

from __future__ import annotations

import base64
import time

from awp.cdp import CDP, frames_of

WIDTH, HEIGHT = 1280, 832
KEYS = {"Enter": ("Enter", 13, "\r"), "Tab": ("Tab", 9, "\t"), "Escape": ("Escape", 27, ""), "Backspace": ("Backspace", 8, "")}


class Browser:
    def __init__(self, deadline_s, width=WIDTH, height=HEIGHT):
        self.width, self.height = width, height
        self.cdp = CDP(deadline_s, extra_flags=(f"--window-size={width},{height + 100}", "--hide-scrollbars", "--force-device-scale-factor=1"))
        self.target = self.session = None
        self.children = {}  # sessionId -> targetId of attached child frames

    # ---------------------------------------------------------------- pages
    def open(self, url, settle_s=0.8):
        self.target, self.session = self.cdp.open_page("about:blank", settle_s=0.1)
        s = self.session
        self.cdp.call("Emulation.setDeviceMetricsOverride", {"width": self.width, "height": self.height, "deviceScaleFactor": 1, "mobile": False}, session=s)
        self.cdp.call("DOM.enable", session=s)
        self.cdp.call("Runtime.enable", session=s)
        self.cdp.call("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True}, session=s)
        self.goto(url, settle_s)
        return self

    def goto(self, url, settle_s=0.8):
        self.cdp.call("Page.navigate", {"url": url}, session=self.session)
        self.cdp.wait_event("Page.loadEventFired", self.session)
        time.sleep(settle_s)
        self._collect_children()

    def _collect_children(self):
        for m in list(self.cdp.events):
            if m.get("method") == "Target.attachedToTarget":
                info = m["params"]["targetInfo"]
                sid = m["params"]["sessionId"]
                if info.get("type") == "iframe" and sid not in self.children:
                    self.children[sid] = info["targetId"]
                    for method in ("Page.enable", "DOM.enable", "Runtime.enable", "Accessibility.enable"):
                        try:
                            self.cdp.call(method, session=sid)
                        except (RuntimeError, TimeoutError):
                            pass
                self.cdp.events.remove(m)
            elif m.get("method") == "Target.detachedFromTarget":
                self.children.pop(m["params"].get("sessionId"), None)
                self.cdp.events.remove(m)

    def switch_to_newest_page(self, settle_s=1.0):
        """Drive the most recently opened page target (a link with target=_blank), attaching a session to it; returns True if one was found."""
        try:
            infos = [ti for ti in self.cdp.call("Target.getTargets").get("targetInfos", []) if ti.get("type") == "page" and ti.get("targetId") != self.target]
        except (RuntimeError, TimeoutError):
            return False
        if not infos:
            return False
        ti = infos[-1]
        s = self.cdp.call("Target.attachToTarget", {"targetId": ti["targetId"], "flatten": True})["sessionId"]
        for method in ("Page.enable", "Accessibility.enable", "DOM.enable", "Runtime.enable"):
            self.cdp.call(method, session=s)
        self.cdp.call("Emulation.setDeviceMetricsOverride", {"width": self.width, "height": self.height, "deviceScaleFactor": 1, "mobile": False}, session=s)
        self.target, self.session, self.children = ti["targetId"], s, {}
        time.sleep(settle_s)
        return True

    def close_other_pages(self):
        """Close page targets other than the driven one (links with target=_blank open new tabs; their requests still reach the sinks)."""
        closed = 0
        try:
            for ti in self.cdp.call("Target.getTargets").get("targetInfos", []):
                if ti.get("type") == "page" and ti.get("targetId") != self.target:
                    self.cdp.call("Target.closeTarget", {"targetId": ti["targetId"]})
                    closed += 1
        except (RuntimeError, TimeoutError):
            pass
        return closed

    def hover(self, x, y):
        self.cdp.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}, session=self.session)

    def scroll_into_view(self, selector):
        return self.eval_js(
            f"(function(){{var e=document.querySelector({selector!r}); if(!e) return null; e.scrollIntoView({{block:'center'}}); var r=e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]}})()"
        )

    def close_page(self):
        if self.target:
            try:
                self.cdp.close_page(self.target)
            except (RuntimeError, TimeoutError):
                pass
        self.target = self.session = None
        self.children = {}

    def close(self):
        self.cdp.close()

    # ---------------------------------------------------------------- observation
    def screenshot(self, path=None):
        data = base64.b64decode(
            self.cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}, session=self.session, timeout_s=30)["data"]
        )
        if path:
            with open(path, "wb") as fh:
                fh.write(data)
        return data

    def frames(self):
        return frames_of(self.cdp.call("Page.getFrameTree", session=self.session)["frameTree"])

    def url(self):
        return self.eval_js("location.href")

    def eval_js(self, expression, session=None, retries=3):
        """Evaluate in the page; a navigation in flight makes DevTools answer 'Inspected target navigated or closed' (seen on the chat client's
        login redirect, 2026-10-19), so the call is retried after a short settle."""
        for attempt in range(retries):
            try:
                return self.cdp.call("Runtime.evaluate", {"expression": expression, "returnByValue": True}, session=session or self.session)["result"].get(
                    "value"
                )
            except RuntimeError as e:
                if "navigated or closed" not in str(e) or attempt == retries - 1:
                    raise
                time.sleep(0.8)
        return None

    def marked_regions(self):
        """The boxes the application's own code verifies as its own (E3 container mark, METHOD.md §7): read from the top document's
        __awp_marked__, which only the application's script defines. An empty list where the application does not mark, or the page is not ours."""
        try:
            out = self.eval_js("window.__awp_marked__ ? window.__awp_marked__() : []")
        except (RuntimeError, TimeoutError):
            return []
        return [[float(v) for v in box] for box in (out or []) if isinstance(box, (list, tuple)) and len(box) == 4]

    def principal_of_box(self, box, marked=None, frame_origin=None, app_origin=None):
        """The provenance policy's one question (METHOD.md §7 E3): who drew the region. application: inside a verified mark in the top
        document (L1 primitive); content: anywhere else in the top document, or in a frame whose origin is not the application's (L2)."""
        if frame_origin is not None and app_origin is not None and frame_origin != app_origin:
            return "content"
        marked = self.marked_regions() if marked is None else marked
        if not box:
            return "unknown"
        cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
        for mx, my, mw, mh in marked:
            if mx <= cx <= mx + mw and my <= cy <= my + mh:
                return "application"
        return "content"

    def ax_snapshot(self, max_nodes=160, max_chars=6000, principal=False):
        """The structured half of a structured observation (METHOD.md §2): the page's own accessibility tree, frame by frame, with each
        frame's origin and url and each node's role, name and box. This is what the browser exposes and nothing more: at an inline content region
        the foreign nodes sit in the main frame under the application's own origin, which is the collapse; in a framed region they carry their own
        frame's origin. Nodes without a useful role are dropped, names are trimmed, and the whole is capped so the prompt stays bounded."""
        out, n = [], 0
        frames = self.frames()
        by_id = {f["id"]: f for f in frames}
        marked = self.marked_regions() if principal else []
        app_origin = next((f.get("origin") for f in frames if not f.get("parent")), None)
        for fr in frames:
            label = "main" if not fr.get("parent") else "child"
            url = fr.get("url") or ""
            head = f'frame {label} origin={fr.get("origin") or "?"} url={url[:90]}'
            if label == "child":
                head += f' parent_origin={(by_id.get(fr.get("parent")) or {}).get("origin") or "?"}'
            out.append(head)
            for node in self.cdp.ax_nodes(self.session, fr["id"]):
                role = (node.get("role") or {}).get("value")
                if not role or role in ("none", "generic", "InlineTextBox", "StaticText"):
                    continue
                name = ((node.get("name") or {}).get("value") or "").strip().replace("\n", " ")
                box = ""
                bid = node.get("backendDOMNodeId")
                if bid:
                    try:
                        q = self.cdp.call("DOM.getBoxModel", {"backendNodeId": bid}, session=self.session)["model"]["content"]
                        xs, ys = q[0::2], q[1::2]
                        box = f" ({round(min(xs))},{round(min(ys))},{round(max(xs) - min(xs))},{round(max(ys) - min(ys))})"
                    except (RuntimeError, TimeoutError, KeyError):
                        box = ""
                who = ""
                if principal:
                    b = [float(v) for v in box.strip(" ()").split(",")] if box else None
                    who = f" principal={self.principal_of_box(b, marked=marked, frame_origin=fr.get('origin'), app_origin=app_origin)}"
                out.append(f'  {role} "{name[:60]}"{box}{who}' if name else f"  {role}{box}{who}")
                n += 1
                if n >= max_nodes:
                    out.append(f"  ... capped at {max_nodes} nodes")
                    break
        text = "\n".join(out)
        return text if len(text) <= max_chars else text[:max_chars] + f"\n... capped at {max_chars} characters"

    # ---------------------------------------------------------------- actions through the input channel
    def click(self, x, y):
        s = self.session
        self.cdp.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}, session=s)
        self.cdp.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}, session=s)
        self.cdp.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}, session=s)

    def type_text(self, text):
        self.cdp.call("Input.insertText", {"text": text}, session=self.session)

    def key(self, name):
        key, vk, text = KEYS[name]
        s = self.session
        self.cdp.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": key, "windowsVirtualKeyCode": vk, "text": text}, session=s)
        self.cdp.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": key, "windowsVirtualKeyCode": vk}, session=s)

    # ---------------------------------------------------------------- element location for scripted agents
    def _owner_box(self, frame_id):
        """Where a child frame's viewport sits in the page: the owning iframe element's content box in the main frame."""
        try:
            owner = self.cdp.call("DOM.getFrameOwner", {"frameId": frame_id}, session=self.session)
            quad = self.cdp.call("DOM.getBoxModel", {"backendNodeId": owner["backendNodeId"]}, session=self.session)["model"]["content"]
            return quad[0], quad[1]
        except (RuntimeError, TimeoutError, KeyError):
            return 0.0, 0.0

    def find(self, name=None, role=None, exact=False):
        """Return matches [{'role','name','x','y','frame'}] from every frame of the page, in page pixels.
        Same-process child frames (two loopback ports are one site, so Chromium keeps the L2 frame in-process) are read by frame id through the
        page session, as the pilot did, and their boxes already come in page coordinates; out-of-process frames, when they occur, are read through
        their own attached session and offset by the owning element's box."""
        out = []
        sources = []
        for fr in self.frames():
            label = "main" if not fr.get("parent") else "child"
            sources.append(
                (self.session, fr["id"], label, (0.0, 0.0))
            )  # same-process frames: DOM.getBoxModel already reports page coordinates (measured 2026-10-19)
        for sid, tid in self.children.items():
            sources.append((sid, None, "child-oopif", self._owner_box(tid)))
        seen = set()
        for sid, frame_id, label, (ox, oy) in sources:
            nodes = self.cdp.ax_nodes(sid, frame_id) if frame_id else self.cdp.ax_nodes(sid)
            for n in nodes:
                r = (n.get("role") or {}).get("value")
                nm = (n.get("name") or {}).get("value") or ""
                if role and r != role:
                    continue
                if name and not (nm == name if exact else name.lower() in nm.lower()):
                    continue
                bid = n.get("backendDOMNodeId")
                if not bid or (sid, bid) in seen:
                    continue
                seen.add((sid, bid))
                try:
                    q = self.cdp.call("DOM.getBoxModel", {"backendNodeId": bid}, session=sid)["model"]["content"]
                except (RuntimeError, TimeoutError, KeyError):
                    continue
                xs, ys = q[0::2], q[1::2]
                out.append(
                    {
                        "role": r,
                        "name": nm,
                        "x": ox + sum(xs) / 4,
                        "y": oy + sum(ys) / 4,
                        "frame": label,
                        "session": sid,
                        "box": [ox + min(xs), oy + min(ys), max(xs) - min(xs), max(ys) - min(ys)],
                    }
                )
        return out

    def dom_box(self, selector):
        """Content box of the first element matching selector, searched through same-process frames (DOM.getDocument pierce), page pixels; None if absent."""
        try:
            root = self.cdp.call("DOM.getDocument", {"depth": -1, "pierce": True}, session=self.session)["root"]["nodeId"]
            nid = self.cdp.call("DOM.querySelector", {"nodeId": root, "selector": selector}, session=self.session)["nodeId"]
            if not nid:
                return None
            q = self.cdp.call("DOM.getBoxModel", {"nodeId": nid}, session=self.session)["model"]["content"]
        except (RuntimeError, TimeoutError, KeyError):
            return None
        xs, ys = q[0::2], q[1::2]
        return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]

    def prompt_box(self, titles=("Session expired", "Allow access?", "Confirm payment", "Update available")):
        """The rendered prompt's box in page pixels: the .awp-prompt element through the DOM (main document and inline content), else the dialog
        node named by the prompt's title in the accessibility tree of a child frame (the framed replica keeps its role). None if absent."""
        box = self.dom_box(".awp-prompt")
        if box:
            return {"box": [round(v, 1) for v in box], "via": "dom"}
        for title in titles:
            hits = [h for h in self.find(name=title) if h["role"] == "dialog"] or [h for h in self.find(name=title) if h["box"][2] > 200 and h["box"][3] > 80]
            if hits:
                return {"title": title, "box": [round(v, 1) for v in hits[0]["box"]], "frame": hits[0]["frame"], "role": hits[0]["role"], "via": "ax"}
        return None
