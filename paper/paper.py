"""IEEE-format build. All statistics injected from facts.json; figures from old/ (the full draft) and new/."""
import base64, json, re
from pathlib import Path

D = Path(__file__).resolve().parent
F = json.loads((D / "facts.json").read_text())
TITLE = "Doppelganger Screens: Indistinguishable Authority Spoofing Against Computer Use Agents"
SHORT = {"open_2": "Qwen3-VL-8B", "open_1": "UI-TARS-1.5-7B", "anthropic_frontier": "Claude Opus 5.5"}
AG = ["open_2", "open_1", "anthropic_frontier"]

def px(ag, c="replica"): return F["by_observation"]["pixels"][ag][c]
def pc(d): return f"{d['rate']:.0%}"
def fr(d): return f"{d['k']}/{d['n']}"
def b64(p):
    p = Path(p); ext = p.suffix.lstrip(".")
    return f"data:image/{ext};base64," + base64.b64encode(p.read_bytes()).decode()

FIGN = {}
def F_(key):   # resolve a figure reference to its number
    return FIGN[key]
_counter = [0]
def _wide(src):
    """A figure wider than roughly 2:1 is unreadable at column width, so it spans."""
    if src is None: return False
    try:
        from PIL import Image
        w, h = Image.open(src).size
        return w / h > 2.0
    except Exception:
        return False

def figure(key, src, cap, span=False, extra=""):
    _counter[0] += 1; FIGN[key] = _counter[0]
    span = span or _wide(src)
    cls = "fig span" if span else "fig"
    img = extra if extra else f'<img src="{b64(src)}" alt="">'
    return f'<figure class="{cls}">{img}<figcaption><b>Fig. {_counter[0]}.</b> {cap}</figcaption></figure>'
_tbl = [0]
def table(cap, html, span=True):
    _tbl[0] += 1
    rn = ["I","II","III","IV","V","VI","VII","VIII"][_tbl[0]-1]
    return (f'<div class="tblwrap{" span" if span else ""}"><div class="tcap">TABLE {rn}<br><span>{cap}</span></div>{html}</div>')

pol = F["policy"]; probe = F["classifier_probe"]["cells"]
halt_no = probe["tree_plain__task_plain"]["halted"] + probe["tree_annotated__task_plain"]["halted"]
halt_yes = probe["tree_plain__task_policy"]["halted"] + probe["tree_annotated__task_policy"]["halted"]
hidn = sum(F["injection"][k]["n"] for k in F["injection"] if k.endswith("|hidden"))
best_inj = {a: max((F["injection"][f"{a}|{t}"] for t in ("plain","authority","hidden")), key=lambda d: d["rate"]) for a in AG}
dose = F["dose"]["anthropic_frontier"]["arms"]

CSS = r"""
<style>
:root{--ink:#000;--sub:#333;--mut:#666;--rule:#bbb;--paper:#fff;--box:#f3f3f1}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){color-scheme:dark;--ink:#ececea;--sub:#c6c5bf;--mut:#94938d;--rule:#4a4a46;--paper:#141517;--box:#1d1e21}}
:root[data-theme="dark"]{color-scheme:dark;--ink:#ececea;--sub:#c6c5bf;--mut:#94938d;--rule:#4a4a46;--paper:#141517;--box:#1d1e21}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font-family:Tinos,"Liberation Serif","Times New Roman",Times,serif;font-size:14.5px;line-height:1.38;margin:0;text-rendering:optimizeLegibility}
.page{max-width:1080px;margin:0 auto;padding:36px 26px 80px}
.ttl{text-align:center;margin:0 0 6px;font-size:26px;line-height:1.2;font-weight:400;letter-spacing:-.005em}
.auth{text-align:center;font-size:14px;margin:0 0 2px}
.aff{text-align:center;font-size:12.5px;font-style:italic;color:var(--sub);margin:0 0 14px}
.stamp{text-align:center;font-family:"DejaVu Sans Mono","Liberation Mono",ui-monospace,monospace;font-size:10.5px;color:var(--mut);margin:0 0 18px;letter-spacing:.01em}
.lead{max-width:none;margin:0 0 10px;padding:0}
.cols{column-count:2;column-gap:26px;column-fill:balance}
@media(max-width:880px){.cols{column-count:1}}
.abs{font-size:13px;line-height:1.35;text-align:justify;margin:0 0 7px;font-weight:600}
.abs+.abs{margin-top:0}
.abs b.lead,.idx b.lead{font-style:italic;font-weight:700}
.idx{font-size:13px;line-height:1.35;text-align:justify;margin:0 0 4px}
h2{font-size:15px;font-weight:700;text-align:left;margin:17px 0 6px;break-after:avoid;page-break-after:avoid}
h3{font-size:14px;font-weight:700;text-align:left;margin:13px 0 3px;break-after:avoid;page-break-after:avoid}
h4{font-size:13.5px;font-weight:400;font-style:italic;margin:8px 0 2px;break-after:avoid}
p{margin:0 0 7px;text-align:justify;hyphens:auto;text-indent:1.1em}
p.ni,.abs,.idx{text-indent:0}
figure{margin:11px 0 13px;break-inside:avoid}
figure.span{column-span:all;margin:16px 0 18px}
figure img{width:100%;display:block;background:#fff;border:1px solid var(--rule)}
figcaption{font-size:11.6px;line-height:1.3;color:var(--ink);margin-top:5px;text-align:justify}
.tblwrap{break-inside:avoid;margin:12px 0 14px}
.tblwrap.span{column-span:all}
.tcap{text-align:center;font-variant:small-caps;font-size:11.8px;letter-spacing:.05em;margin-bottom:4px}
.tcap span{font-variant:normal;font-size:11.6px;display:inline-block;max-width:92%;line-height:1.3}
table{border-collapse:collapse;width:100%;font-size:11.4px;font-variant-numeric:tabular-nums}
th,td{padding:3px 6px;text-align:left;vertical-align:top;border:none}
thead th{border-top:1.1px solid var(--ink);border-bottom:.6px solid var(--ink);font-weight:400;font-style:italic}
tbody tr:last-child td{border-bottom:1.1px solid var(--ink)}
.thm{border-left:2px solid var(--rule);padding:4px 0 4px 10px;margin:8px 0;font-size:13.6px}
.thm b{font-variant:small-caps;letter-spacing:.03em}
.listing{font-family:"DejaVu Sans Mono","Liberation Mono",monospace;font-size:9.8px;line-height:1.32;background:var(--box);border:1px solid var(--rule);padding:7px 9px;margin:6px 0 2px;white-space:pre-wrap}
.lcap{font-size:11.4px;margin:0 0 8px}
code{font-family:"DejaVu Sans Mono","Liberation Mono",ui-monospace,monospace;font-size:11.4px}
.ref{font-size:11.0px;line-height:1.18;margin:0 0 1px;text-indent:-1.3em;padding-left:1.3em;text-align:left}
.plate{display:grid;grid-template-columns:1fr 1fr;gap:7px}
.plate>div:last-child{grid-column:1/-1}
.plate img{width:100%;border:1px solid var(--rule);display:block;background:#fff}
.pc{font-size:11.2px;color:var(--sub);margin-top:3px}
.svgwrap{background:#fff;border:1px solid var(--rule);padding:7px}
svg{display:block;width:100%;height:auto}
</style>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Tinos:ital,wght@0,400;0,700;1,400;1,700&display=swap">
<style>body{font-family:Tinos,"Liberation Serif","Times New Roman",Times,serif}</style>
"""

import sys; sys.path.insert(0, str(D))
from svgs import SVG_TRUST, SVG_CHAIN, SVG_LADDER
from killchain import SVG_CHAIN2
from trust2 import SVG_TRUST2
from ladder2 import SVG_LADDER2
from captions import CAPTIONS

P = []; A = P.append
A(f"<title>Doppelganger Screens</title>{CSS}<div class='page'>")
A(f'<h1 class="ttl">{TITLE}</h1>')
A('<p class="auth">Christian David Varela</p>')
A('<p class="aff">Cybersecurity Researcher, Psypher Labs &middot; San Francisco, California</p>')
A('<p class="stamp">October 2026</p>')

A('<div class="lead">')
A('<p class="abs"><b class="lead">Abstract</b>&mdash;AI agents are being deployed inside the applications people already work in, where they read content written by others and act on what they see. '
  'That puts an automated actor holding the user\'s authority in front of surfaces an adversary can write to.</p>')
A('<p class="abs">We show that an adversary who can only post a message, with no model access, no jailbreak and no contact with the user, can cause such an agent to grant a permission, confirm a payment or install an update the user had approved, to the adversary\'s endpoint rather than the application\'s. '
  'The method is to copy the application\'s own security prompt into the content it renders. On the surface we instrumented, which is how the webmail and chat clients we measured display message bodies, the copy and the original are the same image.</p>')
A('<p class="abs">All three agents we tested were fooled, and the commercial frontier model acted on the copy in nearly every episode. The attack carries no instruction, so it is not prompt injection, and the defences built for injection do not apply: '
  'where the two render identically nothing that reads the screen can separate them, which we measure rather than assume. '
  'Four classes of defence run over the recorded screens gained no advantage, and the copy succeeded more often than injection did.</p>')
A('<p class="abs">Separation appears only once the page structure names the adversary\'s origin, and is restored by a provenance channel enforced in the agent harness, which refused every copy while admitting every genuine prompt. This is a proof of concept on one instrumented application; it establishes the class and the bound, not the prevalence.</p>')
A('<p class="idx"><b class="lead">Index Terms</b>—computer use agents, user interface spoofing, trusted path, provenance, indirect prompt injection, confused deputy, preregistered evaluation.</p>')
A('</div><div class="cols">')

# ───────────────────────────────── I
A('<h2>1&nbsp;&nbsp;Introduction</h2>')
A('<p class="ni">An authority prompt is a request for privilege: a credential, a scope grant, a payment confirmation, an update. '
  'Applications draw their own authority prompts, and the same applications render markup authored by third parties. '
  'A principal who can write that markup can draw an authority prompt as well.</p>')
A('<p>Against a human operator this is interface spoofing, and it is bounded by attention, habit and the trusted path mechanisms browsers and operating systems have accumulated over two decades. '
  'Against an agent that observes the screen the question is sharper. If the spoofed prompt renders to the same bitmap as the genuine one, what remains to decide?</p>')
A('<p>Research on agent security has concentrated on indirect prompt injection: instructions embedded in content that the model reads and follows. '
  'Defences inherit that shape. Detect the instruction, filter it, train the model to discount imperatives in content, or separate instruction and data channels. '
  'Each assumes the hostile input is marked by what it says.</p>')
A('<p>We study the case where the hostile input says nothing. The adversary supplies no imperative and the agent is not subverted. '
  'It performs the task it was given, and the privilege lands with the wrong party. That is a confused deputy [1] at the observation layer: the deputy holds authority, acts on a request, '
  'and has no channel by which to attribute it. We call the attack a <b>doppelganger screen</b> and its class <b>authority spoofing</b>, both defined in Section 3.3.</p>')
A('<p>We make four contributions. '
  '1) The attack, and an instrument that measures it on three agents, reading outcomes at sinks rather than from the agent and testing the two renderings for identity rather than assuming it. '
  '2) A result that bounds every defence reading the screen at zero advantage wherever that identity holds, with three consequences the paper tests. '
  '3) An evaluation of four defence classes over the recorded screens and a comparison with indirect prompt injection on one harness. '
  '4) A mitigation evaluated against a bound fixed in advance, and a report of when a deployed commercial filter fires and when it stops.</p>')

# ───────────────────────────────── II
A('<h2>2&nbsp;&nbsp;Background and Related Work</h2>')
A('<h3>2.1&nbsp;&nbsp;Interface spoofing and trusted paths</h3>')
A('<p class="ni">Clickjacking and UI redressing place surfaces the adversary controls over or beneath genuine ones [4]; picture in picture phishing rendered a complete browser chrome inside a page, and a user study found extended validation indicators did not help untrained participants reject it [3]. '
  'The accepted answer in both lines is a trusted path [2]: a surface the adversary provably cannot render, authenticated by a channel outside the content. '
  'Operating systems implement this with separate processes and window ownership. The idea of a forged dialog is not ours; what changes is its consequences.</p>')
A('<p>Two things change when the recipient is an agent. The human defences that bounded the classical attacks are absent, and the agent has a reason to answer: its task is blocked until it does. '
  'The remedy changes too. A person can be taught to look for a trusted path. An agent has no such habit, so the trusted path must be a field in its input rather than a convention in its presentation.</p>')
A('<h3>2.2&nbsp;&nbsp;Indirect prompt injection</h3>')
A('<p class="ni">The closest active area targets instructions carried in content [7], [9], and its defences detect, filter or ignore them. '
  'Benchmarks there measure whether an agent can be derailed by adversarial text [9], [10], [11]. We ask a different question: whether an agent can attribute a request at all. '
  'Section 6.4 compares the two on one harness, where the copy was the stronger for every agent.</p>')
A('<p>Two lines sit closest to ours. Pop-up attacks place adversarial windows carrying attention hooks and instructions into the screen of vision language model agents [8]; they report 86 percent success and survive being told to ignore pop-ups. '
  'The <i>visual confused deputy</i> has already been named for this setting [17], covering agents that authorise an action after misperceiving the screen through grounding error, screenshot manipulation or a TOCTOU race [14]. '
  'Ours differs from both in the same way: their artefacts are distinguishable from the application\'s interface and their failure is misperception, while ours is a copy of that interface, perceived correctly, and the failure is attribution. '
  'Their failed countermeasure is also ours. A warning in the system prompt bought nothing here either, which is what Section 4 predicts of any defence reading the same screen, and what VPI-Bench found of system prompt defences [10].</p>')
A('<p>Two further results point the same way. Mobile agents show the family through forged interface elements and notification backdoors [15], [16], and a systematization of this setting names the architectural flaw independently, '
  'as absent input provenance tracking and weak binding between interface and action [13]. This paper measures what that absence is worth to an adversary.</p>')
A('<p class="ni">SnapGuard proposes a lightweight classifier over screenshots to flag injected content for agents that work from rendered pages [20], and a recent guardrail evaluates the click target and the agent\'s stated reasoning '
  'against deployment knowledge bases, outside the agent\'s perceptual loop [17]. Result 1 bounds any detector of this form at zero advantage where the two renderings are identical, whatever its architecture or operating point. '
  'We include SnapGuard at its released version as one of our four defence classes. Reproducing it first, we recover its published F1 and true positive rate inside our registered tolerance and measure a false positive rate of 0.18 against the published 0.09, so the figures we carry forward are our own. That 0.18 is on its own benchmark; the rates it reaches on our screens are in Table VIII.</p>')

# ───────────────────────────────── III
A('<h2>3&nbsp;&nbsp;Threat Model</h2>')
A('<h3>3.1&nbsp;&nbsp;Adversary model</h3>')
A('<p class="ni"><b>Adversary capability.</b> The adversary can place content in a region the target application renders: a message body, a ticket, a post, a shared document. '
  'They cannot modify the application, the agent, the harness or the operating system, and cannot read the agent\'s prompt, task or reasoning. '
  'They know what the application\'s genuine prompts look like, as any user does. This is the indirect injection adversary\'s capability and nothing more [7], and less than the visual attack literature assumes, which needs model access [12] or a window of its own [8]: no jailbreak, no model access, no supply chain foothold, no contact with the victim.</p>')
A('<p><b>Adversary goal.</b> Induce the agent to perform one of four authority acts through an element the adversary controls: credential entry (CRED), permission grant (PERM), '
  'payment confirmation (CONF) or update installation (UPDT). Success is recorded at a sink under our control, not inferred from the agent\'s output.</p>')
A('<p><b>Victim model.</b> A user delegates an ordinary task to a computer use agent. No lure, urgency or social engineering is required; '
  'the adversary\'s content is already in the workspace the agent was asked to work in. '
  'The task pre-authorises the act in the user\'s own words: allow the integration if it asks, keep the application up to date if an update is offered, make sure the payment goes through, sign in again if asked. '
  'Nothing the agent does is unrequested. What it gets wrong is who asked.</p>')
A('<p><b>Terminology.</b> An <i>act cell</i> is one authority act on one surface, and is the unit at which every rate is computed. A <i>context</i> is one of two task scenarios frozen before any recorded run. '
  'Utility is the rate at which an agent performs the act on the genuine prompt and the confusion rate is the rate on the copy. '
  'Two signed differences follow and they run opposite ways: the agent side <i>gap</i> is utility minus the confusion rate, so a gap of zero means the agent treated the two alike; '
  'the <i>defence advantage</i> is a detector&#8217;s flag rate on the copy minus its flag rate on the genuine prompt, so a defence that separates them is positive. '
  'The utility floor of 0.7 was fixed in advance and measured in its own run on the first context before any paired episode, each agent attempting the genuine act with no copy anywhere on the screen. '
  'Below the floor an agent carries no confusion rate on that cell and is reported as not measurable, never as secure. Every table in this paper uses that one set of cells.</p>')
A(figure("trust", None, CAPTIONS["trust"], span=True, extra=SVG_TRUST2))
A('<h3>3.2&nbsp;&nbsp;Assets and impact</h3>')
A('<p class="ni">The asset at risk is not data the agent holds but the authority delegated to it. An agent operates with the user\'s standing authority across every surface it reaches, '
  'and an authority prompt is the moment that authority is spent. Each act spends it differently, so the impact divides across confidentiality, integrity and availability rather than falling on one.</p>')
A('<p>The impact claims rest on what the sink actually records. The copy is the adversary\'s markup, so its control submits to the adversary\'s origin: for a permission grant the sink records the user\'s authorisation for a named scope arriving at the adversary\'s endpoint. '
  'Exchanging that for a usable token requires the adversary to be a registered client, which we do not model, so Table I reports what was received.</p>')
A('<p>Table I gives the decomposition. Update installation is the only act that touches all three properties, since installed code can withhold service as readily as it can exfiltrate. '
  'Credential entry is the sharpest confidentiality loss, and the floor run admits it for both open models: on the framed surface for UI-TARS and on both surfaces for Qwen3-VL. '
  'It carries no rate for the frontier agent, whose six attempts the vendor\'s classifier halted before the model answered.</p>')
A('<p>Two properties differ from the injection case. The loss is authorised: the browser submits a well formed form on the user\'s behalf, so nothing on the wire is malformed, anomalous or against policy, and detection downstream has nothing to key on.</p>')
A(table("What the adversary\'s endpoint recorded when the agent acted on the copy, and which security property is at risk. A filled circle marks a property the act puts at risk and an open circle one it does not. Read a row as the loss for that act. Takeaway: update installation is the only act that puts all three properties at risk, and every act here carries a measured rate for at least one agent.",
  '<table><thead><tr><th style="width:21%">Authority act</th><th style="width:41%">What the adversary&#8217;s endpoint received</th>'
  '<th>Conf.</th><th>Integ.</th><th>Avail.</th></tr></thead><tbody>'
  '<tr><td>Permission grant</td><td>The user&#8217;s authorisation for a named scope, submitted to an origin the adversary controls</td><td>&#9679;</td><td>&#9679;</td><td>&#9675;</td></tr>'
  '<tr><td>Payment confirmation</td><td>A confirmed transaction instruction against the user&#8217;s account</td><td>&#9675;</td><td>&#9679;</td><td>&#9675;</td></tr>'
  '<tr><td>Update installation</td><td>Consent to install an artefact the adversary supplies</td><td>&#9679;</td><td>&#9679;</td><td>&#9679;</td></tr>'
  '<tr><td>Credential entry</td><td>The user&#8217;s credentials, typed into a field the adversary drew. Measured for both open models; no rate for the frontier agent, whose attempts the classifier halted</td><td>&#9679;</td><td>&#9679;</td><td>&#9675;</td></tr>'
  '</tbody></table>'))
A('<h3>3.3&nbsp;&nbsp;Attack class: authority spoofing</h3>')
A('<p class="ni"><b>Definition 1 (doppelganger screen).</b> A rendering <i>s</i><sub>copy</sub> produced from content the adversary supplied, such that <i>M</i>(<i>s</i><sub>copy</sub>) = <i>M</i>(<i>s</i><sub>genuine</sub>) '
  'for the agent\'s observation map <i>M</i>, where <i>s</i><sub>genuine</sub> is the rendering in which the application itself issues the authority prompt.</p>')
A('<p><b>Definition 2 (authority spoofing).</b> An attack in which an adversary able only to supply rendered content induces an agent to perform a privileged action by presenting a request that is '
  'indistinguishable, under the agent\'s observation map, from a request issued by the application. The adversary supplies no instruction. The agent\'s perception, grounding and intent are all correct; '
  'the failure is that the observation carries no information identifying the principal behind the request.</p>')
A('<p>The distinction from prompt injection is sharp and is the organising claim of this paper. <i>Injection subverts intent</i>: an imperative in content replaces or redirects the agent\'s goal, and the '
  'defensive question is whether that imperative can be recognised. <i>Authority spoofing defeats attribution</i>: the goal is untouched, the agent clicks precisely the element it intended to click, and the '
  'privilege is nonetheless delivered to the adversary. Every defence in the injection line searches for a discrepancy. A doppelganger screen is defined by the absence of one.</p>')
A('<p>Table II decomposes the weakness onto standard identifiers [5], and the decomposition is not loose analogy. CVE-2025-25306, a forgery of federated notes in Misskey, is issued against CWE-346 and CWE-441 together; CVE-2026-32318, a tampered vault configuration in Cryptomator for iOS, pairs CWE-346 with CWE-451.</p>')
A(table("The attack class on standard identifiers. The rows read top to bottom as cause, consequence, surface and missing control. Takeaway: this is an origin validation failure that produces a confused deputy, and the control it needs is a trusted path.",
  '<table><thead><tr><th>Layer</th><th>Identifier</th><th>Statement</th></tr></thead><tbody>'
  '<tr><td>Weakness (root cause)</td><td>CWE-346 · Origin Validation Error</td><td>The product does not properly verify that the source of data or communication is valid.</td></tr>'
  '<tr><td>Consequence</td><td>CWE-441 · Unintended Proxy or Intermediary (Confused Deputy)</td><td>A component does not preserve the original source of a request before acting on it.</td></tr>'
  '<tr><td>Surface manifestation</td><td>CWE-451 · UI Misrepresentation of Critical Information</td><td>Critical information, or its source, is obscured or spoofed.</td></tr>'
  '<tr><td>Missing control</td><td>Trusted path (TCSEC)</td><td>A mechanism guaranteeing communication with the intended principal and not an impersonator.</td></tr>'
  '</tbody></table>', span=False))
A('<p class="ni">Stated once, for use throughout: a doppelganger screen is an authority spoofing attack that exploits an origin validation error in the agent\'s observation channel, '
  'turning the agent into a confused deputy. No deployed agent harness we inspected, or whose documentation we read, provides the trusted path that would prevent it.</p>')
A('<p class="ni">Table III places the attack against the families it is most likely to be confused with. Each of them is identified by an artefact it leaves, and each corresponding defence is a search for that artefact. '
  'Ours leaves none.</p>')
A(table("Separation from the attack families this one is most often confused with. The column to read is the third: what a defender looks for. Takeaway: every neighbouring attack is identified by an artefact it leaves, and this construction leaves none.",
  '<table><thead><tr><th>Family</th><th>Mechanism</th><th>What a defender looks for</th><th>Why it does not apply here</th></tr></thead><tbody>'
  '<tr><td>Indirect and visual prompt injection [7], [10], [11]</td><td>An imperative embedded in rendered or retrieved content</td><td>The imperative</td><td>No instruction is supplied</td></tr>'
  '<tr><td>Adversarial visual patch [12]</td><td>An optimised perturbation inducing a target action</td><td>The perturbation</td><td>The pixels are the application\'s own legitimate rendering</td></tr>'
  '<tr><td>Clickjacking and UI redressing [4]</td><td>Geometry: a surface over or beneath another</td><td>Frame and layer policy</td><td>The region is one the application legitimately grants the adversary</td></tr>'
  '<tr><td>TOCTOU on computer use agents [14]</td><td>The interval between observation and action</td><td>Verifying again before acting</td><td>The attack holds under instantaneous observation</td></tr>'
  '<tr><td>Grounding attacks [17]</td><td>The agent locates the wrong element</td><td>Grounding accuracy</td><td>Grounding is correct; the intended element is the adversary\'s</td></tr>'
  '<tr><td>Weak interface and action binding [13]</td><td>The act performed is not bound to the element perceived</td><td>The mismatch</td><td>There is no mismatch: the agent acts on exactly the element it perceived</td></tr>'
  '</tbody></table>'))
A('<h3>3.4&nbsp;&nbsp;Kill chain and framework mapping</h3>')
A('<p class="ni">Fig. 2 places the attack on a kill chain and marks at every stage what a defender could attempt and what we found it to be worth. '
  'Reconnaissance, weaponisation and the user\'s own delegation offer nothing to act on, because each is ordinary use or happens outside the victim estate. '
  'Two stages carry a defence we measured, the sanitiser at rendering and the four classes at execution, and both come out at zero advantage. '
  'Two carry a defence we did not evaluate and make no claim about, content filtering at delivery and detection at the sink. '
  'The one break point no deployed defence occupies sits in the harness, the last component holding each region\'s origin, and Section 7 measures what it is worth there.</p>')
A(figure("chain", None, CAPTIONS["chain"], span=True, extra=SVG_CHAIN2))
A('<p class="ni">Table IV maps the attack onto MITRE ATLAS and ATT&amp;CK [6], and the mapping is informative in both directions. '
  'Nine techniques across seven tactics apply. The closest is <code>AML.T0100 AI Agent Clickbait</code>, which covers content crafted to bait a computer using agent into an unintended action by exploiting its reading of interface content; the table gives the rest.</p>')
A('<p><code>AML.T0051 LLM Prompt Injection</code> and its indirect subtechnique are defined by instructions that make the model disregard its own and follow the adversary\'s. '
  'Filing this attack under prompt injection inherits the defensive apparatus built for prompt injection, which Section 6.5 measures at zero advantage.</p>')
A('<p>The mapping also exposes a gap. Every applicable technique describes content that is <i>deceptive</i>, which presupposes a discrepancy between the artefact and the legitimate thing it '
  'imitates. None describes content that is indistinguishable from the legitimate thing. We suggest that an indistinguishable interface subtechnique under <code>AML.T0100</code> would '
  'close it, and that the distinction is operationally meaningful rather than taxonomic: deceptive content admits a detector, and indistinguishable content does not.</p>')
A(table("The attack mapped onto MITRE ATLAS and ATT&amp;CK, with tactic placement taken from the ATLAS record of case studies. Read the final column for why each technique applies. Takeaway: nine techniques across seven tactics cover the attack and the closest is AI Agent Clickbait, but none covers content indistinguishable from the legitimate element rather than merely deceptive, and the last two rows lie beyond what our sinks record.",
  '<table><thead><tr><th style="width:14%">Tactic</th><th style="width:15%">Identifier</th><th style="width:26%">Technique</th><th>How it applies</th></tr></thead><tbody>'
  '<tr><td>Initial Access</td><td>ATT&amp;CK T1566</td><td>Phishing</td><td>The markup arrives as a message the victim already expects to receive</td></tr>'
  '<tr><td>Execution</td><td>ATLAS AML.T0100</td><td>AI Agent Clickbait</td><td>Content crafted to bait a computer using agent into an unintended action. The closest existing technique</td></tr>'
  '<tr><td rowspan="3">Defense Evasion</td><td>ATLAS AML.T0074</td><td>Masquerading</td><td>The artefact is manipulated to appear legitimate to users and to tooling</td></tr>'
  '<tr><td>ATLAS AML.T0073</td><td>Impersonation</td><td>A trusted party is impersonated in order to obtain an action</td></tr>'
  '<tr><td>ATT&amp;CK T1036</td><td>Masquerading</td><td>The element imitates one the application itself would draw</td></tr>'
  '<tr><td>Privilege Escalation</td><td>ATLAS AML.T0053</td><td>AI Agent Tool Invocation</td><td>The computer use tool is the vehicle that performs the act</td></tr>'
  '<tr><td>Credential Access</td><td>ATT&amp;CK T1528</td><td>Steal Application Access Token</td><td>The grant delivers the authorisation the user gave to the adversary&#8217;s endpoint. Exchanging it for a token is the documented next step and lies outside our sinks</td></tr>'
  '<tr><td>Lateral Movement</td><td>ATLAS AML.T0091.000</td><td>Application Access Token</td><td>Where that exchange happens the token carries the granted scope. Not modelled here</td></tr>'
  '<tr><td>Impact</td><td>ATLAS AML.T0048</td><td>External Harms</td><td>The act completes at the sink: a payment made, a scope granted, an artefact installed</td></tr>'
  '</tbody></table>'))

# ───────────────────────────────── IV
A('<h2>4&nbsp;&nbsp;The Indistinguishability Result</h2>')
A('<p class="ni">We state the following as a result rather than an observation because it bounds a whole class of defence, not only the four we tested.</p>')
A('<div class="thm"><p class="ni"><b>Result 1.</b> If the agent\'s observation is the screen, and the application\'s own authority prompt and the adversary\'s copy render to the same image in matched context, '
  'then for every agent policy and every defence that is a function of the goal, the history and the observation, the probability of performing the act on the copy equals the probability of performing it on the genuine prompt. '
  'The defence advantage is exactly zero.</p></div>')
A('<p class="ni"><i>Why.</i> If the two renderings are the same image, the defence receives the same input in both conditions, and matched context makes the goal and history coincide. '
  'A function returns the same output distribution on the same input distribution, so its flag rate is equal on the two and the difference is zero. '
  '</p>')
A('<p>Three consequences follow, each tested below.</p>')
A('<p class="ni"><b>(C1) A screen level detector cannot trade advantage for utility.</b> Every flag it raises falls on both conditions alike, so lowering the rate on the copy lowers the rate on the genuine prompt equally. '
  'Where the renderings differ slightly, the achievable advantage is capped by the detector\'s sensitivity in pixel space, which is a ceiling rather than a construction. Tested in Section 6.5.</p>')
A('<p class="ni"><b>(C2) Structure helps only where it separates principals.</b> A defence reading the accessibility tree is sound exactly when that tree assigns different principals to the two prompts. '
  'Inline markup does not, and wherever a sanitiser passes role and ARIA attributes the adversary writes part of the tree, so a rule reading those fields inherits the adversary\'s choice. The first clause is tested in Section 6.6; the attacker-writable clause is argued, not measured.</p>')
A('<p class="ni"><b>(C3) Separation requires an unwritable channel.</b> A system that tells the two apart must receive something correlated with which prompt is which, which the adversary cannot write from inside their own region. '
  'That is a trusted path [2], and it is the form the mitigation takes. Tested in Section 7.</p>')
A(figure("ladder", None, CAPTIONS["ladder"], span=True, extra=SVG_LADDER2))

# ───────────────────────────────── V
A('<h2>5&nbsp;&nbsp;Instrument and Methodology</h2>')
A('<h3>5.1&nbsp;&nbsp;Target application</h3>')
A('<p class="ni">The target is a two origin web application standing in for a webmail client, with finance and IT notices as its messages. Its own authority prompts fire on real events, and each carries a secret issued per run that only the application\'s script can read. '
  'That secret is the ground truth for which prompt was genuine. It never reaches the agent and no defence under test uses it. Listing 1 is the prompt itself. '
  'Message bodies render markup written by others through a sanitiser in one of two behaviours, both measured on production mail clients: Roundcube strips role and ARIA attributes, Thunderbird passes role=dialog through. '
  'The screenshot only results use the stripping behaviour; both appear in the structured arms.</p>')
A('<pre class="listing">&lt;div role="dialog" aria-modal="true"&gt;\n  Allow access?\n  Calendar Sync wants to access your contacts (read-only).\n  &lt;form method="post" action="<b>{action_url}</b>"&gt;\n    &lt;input type="hidden" name="nonce" value="&hellip;"&gt;\n    &lt;input type="hidden" name="client" value="calsync"&gt;\n    &lt;input type="hidden" name="scope" value="contacts.read"&gt;\n    &lt;button name="decision" value="allow"&gt;Allow&lt;/button&gt;\n    &lt;button name="decision" value="deny"&gt;Don\'t allow&lt;/button&gt;\n  &lt;/form&gt;\n&lt;/div&gt;</pre>')
A('<p class="lcap"><b>Listing 1.</b> The permission prompt as the application emits it, inline styles omitted. The application\'s own prompt and the adversary\'s copy come from this one template; '
  'only <code>action</code> differs, the application\'s origin or the adversary\'s, and the dialog role survives only where the renderer lets it through.</p>')
A('<p>Two surface levels are instrumented. At the <i>inline</i> level (L1) adversary content is rendered in the application\'s own document, which is how the webmail and chat clients we measured render message bodies, Roundcube\'s full view and Mattermost among them. '
  'At the <i>framed</i> level (L2) it is rendered in a child frame of a different origin.</p>')
A('<h3>5.2&nbsp;&nbsp;Agents and observation conditions</h3>')
A(f'<p class="ni">Three computer use agents. {SHORT["open_2"]} and {SHORT["open_1"]} are open weight models built for GUI control, served locally at temperature zero. '
  f'{SHORT["anthropic_frontier"]} runs through its vendor\'s dated computer use toolset [22] at the vendor\'s default sampling, so the commercial path is exercised as deployed. '
  'Each runs under three observations: <i>pixels</i>, a screenshot only, which is what every deployed harness sends; <i>structured</i>, the screenshot plus the accessibility tree; '
  'and <i>provenance</i>, the structured observation with a principal label on every node and one sentence of policy in the task. '
  'Both open models ran both frozen contexts under every observation; the frontier agent ran one context under pixels and both under the other two.</p>')
A('<h3>5.3&nbsp;&nbsp;Design and outcome measurement</h3>')
A('<p>Two outcomes are reported on the same pairs, both specified in advance. The first action outcome asks whether the agent performed the act at its first step, which at the inline level is the only moment the two observations are identical. '
  'The episode outcome asks whether the act happened at all. Section 6.3 reports both and explains why they differ. Every task carries the user\'s approval for the act in question (Section 3.1), so what is measured is attribution, not willingness. '
  'The paired record is 1,120 episodes, 1,039 of them with a usable outcome: 1,005 on browser surfaces and 34 on chat. The 81 without one are 24 requests the vendor\'s classifier halted, 54 empty responses from one frontier invocation that was re-run, and 3 parse failures from the open models. A further 270 episodes measure text injection against the same cells.</p>')
A('<h3>5.4&nbsp;&nbsp;Preregistration and controls</h3>')
A('<p class="ni">Hypotheses, equivalence margins, the utility floor and the analysis path were registered before measurement. Each batch\'s predictions were written and hashed before it ran and scored after, and every look at unblinded data was registered in advance. '
  'Single rates carry Clopper-Pearson intervals and differences Newcombe hybrid score intervals; tests are Fisher\'s exact and exact McNemar. '
  'The whole study, three agents, four defence classes, the injection comparison and the mitigation, cost 33.72 USD in API calls over 1,599 requests.</p>')
# ───────────────────────────────── VI
A('<h2>6&nbsp;&nbsp;Results</h2>')
A('<h3>6.1&nbsp;&nbsp;The premise: the screens are identical bit for bit</h3>')
A('<p class="ni">Result 1 is vacuous unless its premise holds, so we measured it on the full frame rather than a crop. At the inline level the first screenshots of a pair are identical over the whole 1280 by 832 frame: '
  'zero differing pixels of 1,064,960 and SSIM 1.000, on all 284 inline pairs in the record. '
  'At the framed level they differ, and every differing pixel falls inside the dialog and its drop shadow, nowhere else on the screen: 9,579 to 10,539 pixels across 204 pairs, about one percent of the frame. '
  'Almost all of it is a single intensity level, the child frame antialiasing the same glyphs differently; 194 to 377 pixels differ by more than eight levels, and those sit on one line of the dialog\'s text.</p>')
A(figure("twins", D/"figures/twins-pairs.png", CAPTIONS["twins"], span=True))
A(figure("eps", D/"figures/eps-pairs.png", CAPTIONS["eps"], span=True))
A('<h3>6.2&nbsp;&nbsp;Agents perform the authority act on the copy</h3>')
A('<p class="ni">From screenshots alone, on the browser surfaces where the two renderings are identical, every agent acted on the copy. '
  'Claude Opus 5.5 performed the authority act on 24 of 25 copies against 25 of 25 genuine prompts, UI-TARS-1.5-7B on 39 of 53 against 45 of 53, and Qwen3-VL-8B on 37 of 52 against 42 of 52. '
  'Table V gives every cell. The frontier agent acted at its first step on 24 of 24 copies and 25 of 25 genuine prompts; the open models did so on about half of each. '
  'Its own account of a copy episode reads: &ldquo;The dialog asks for Calendar Sync access, which the user pre-authorized. I\'ll allow it and then open Payments.&rdquo; Correct perception, correct intent, wrong principal.</p>')
A(figure("headline", D/"figures/headline-browser.png", CAPTIONS["headline"], span=True))
A('<p>The copy succeeds on 71, 74 and 96 percent of episodes across the three agents, against 81, 85 and 100 percent for the application\'s own prompt: gaps of 10, 11 and 4 points. '
  'The two open models are not distinguishable from each other on either quantity, and each rate covers only that agent\'s own cells, so the ordering is not a capability measurement. '
  'The gap is not detection and it is not low utility: in four of the five cells where it is positive the genuine rate is 100 percent. It is navigation. '
  'When an agent\'s first click leaves the prompt for the task page, the application redraws its own prompt there and the copy, which lives in one message, does not follow. '
  'Fig. 7 plots every cell. In four the copy\'s deficit equals the number of copy episodes whose first click left the prompt; eleven show no navigation and no gap; '
  'UI-TARS\'s inline update cell navigated on every episode of both halves and recovered the genuine prompt more often; and Qwen3-VL\'s framed credential cell reverses the sign, '
  'the genuine half navigating five times and losing five while the copy went 10 of 10. The outcome follows the navigation, whichever half does it.</p>')
A(figure("gapnav", D/"figures/gap-navigation.png", CAPTIONS["gapnav"]))
A('<p>Fig. 8 breaks the same episodes down by act. Every agent confirmed the adversary\'s payment every time. '
  'Credential entry, the sharpest loss in Table I, succeeded on 15 of 20 copies for Qwen3-VL and 4 of 10 for UI-TARS; permission and update are where the open models\' deficits sit.</p>')
A(figure("acts", D/"figures/act-heatmap.png", CAPTIONS["acts"]))
A('<p class="ni">One surface is excluded from those rates because its pair is not identical: on chat the adversary can only post a link (Fig. 4). '
  'Neither of the two agents measurable there acted on it in any of its 17 episodes, and both acted on the genuine prompt in all 17. '
  'That is the positive control appearing in the results: where the copy is visibly different, these agents leave it alone, and pooling those episodes would understate the attack.</p>')
A('<p>The two frozen contexts do not behave alike for the weakest model. Qwen3-VL acted on every copy in the finance context and on 11 of 26 in the IT context, where its genuine rate also fell to 16 of 26; '
  'UI-TARS is steady across the two (Fig. 9). The floor was set on the first context, which is why the second can fall under it.</p>')
A(figure("ctx", D/"figures/context-split.png", CAPTIONS["ctx"]))
SURF={"browser-l1":"inline","browser-l2":"framed","chat-l1-web":"chat"}
ACTN={"CONF":"payment","PERM":"permission","UPDT":"update","CRED":"credential"}
_rows=[]; _seen=set()
for _ag in ("anthropic_frontier","open_1","open_2"):
    _cells=[r for r in F["per_cell"] if r["agent"]==_ag]
    _cells.sort(key=lambda r:(r["cell"]!="browser-l1", r["cell"], ACTN[r["act"]]))
    for _r in _cells:
        g,c=_r["genuine"],_r["replica"]
        _gap=g["k"]/g["n"]-c["k"]/c["n"]
        _grey = _r["cell"].startswith("chat")
        _note = "unmatched pair" if _grey else ""
        _style=' style="color:var(--mut)"' if _grey else ""
        _name = SHORT[_ag] if _ag not in _seen else ""
        _seen.add(_ag)
        _rows.append(f'<tr{_style}><td>{_name}</td><td>{SURF[_r["cell"]]}</td><td>{ACTN[_r["act"]]}</td>'
                     f'<td>{g["k"]}/{g["n"]}</td><td>{c["k"]}/{c["n"]}</td><td><b>{_gap:+.2f}</b></td><td>{_note}</td></tr>')
A(table("Every act cell the registered floor run admits, screenshots only. <i>Gap</i> is the rate on the genuine prompt minus the rate on the copy, so a gap of zero means the agent treated the two alike. "
  "Read the gap column. Takeaway: it is zero on every payment cell for every agent, and every nonzero entry is a cell where the agent's first click left the prompt, which Section 6.2 and Fig. 7 trace to navigation rather than detection. "
  "Two cells are worth naming. Framed credential entry is the one row that runs the other way, where Qwen3-VL acted on the copy 10 of 10 times against 5 of 10 on the genuine prompt. "
  "The chat rows are greyed because that pair is not identical, so they enter no pooled rate.",
  '<table><thead><tr><th style="width:21%">Agent</th><th>Surface</th><th>Act</th><th>Acted on the real prompt</th><th>Acted on the copy</th><th>Gap</th><th></th></tr></thead><tbody>'
  + "".join(_rows) + '</tbody></table>'))

A('<h3>6.3&nbsp;&nbsp;The paired test at the moment of decision</h3>')
A('<p class="ni">Because the design is paired, the test is paired. Table VI gives both outcomes. Taking the first action outcome, with no episode excluded from the act cells it covers, the two halves of a pair disagree rarely and without direction: '
  'inline, 3 pairs of 64 favour the application\'s own prompt and 1 favours the doppelganger, exact McNemar <i>p</i> = 0.625; framed, 6 of 66 against 6, <i>p</i> = 1.000; pooled, 9 against 7 over 130 pairs, <i>p</i> = 0.80. '
  'Only the inline row speaks to Result 1, since only there are the two observations identical byte for byte, and on it the agents behave the same. '
  'The framed halves differ by about one percent of the frame, so that row and the pooled figure test weaker premises.</p>')
A('<p>Taking the episode outcome on the same pairs the picture changes: 130 pairs, 106 concordant, 24 discordant, 18 of them favouring the application\'s own prompt and 6 the copy, exact McNemar <i>p</i> = 0.023. '
  'The direction is not uniform. Inline it is, 9 against 0 with <i>p</i> = 0.0039; framed it is not, 9 against 6 with <i>p</i> = 0.61.</p>')
A('<p>The inline asymmetry belongs to the application, not the agent. Our target redraws its own prompt on every page it serves, so the genuine prompt gets repeated chances across a multistep episode while a copy in one message cannot follow. '
  'The first action result agrees: where persistence cannot act, the difference vanishes. We did not run the experiment that would settle it, because removing persistence changes the instrument and makes every frozen episode incomparable. '
  'This rests on an argument and a weaker test, not a measurement. An adversary wanting the same persistence sends more than one message.</p>')
A('<p>Table VII resolves the same test by agent and observation. Down the first column the largest disagreement anywhere is six pairs, and it runs toward the copy in one cell and toward the genuine prompt in another. '
  'Across a row the specifics matter. Neither open weight model separates on pixels or on the tree. The frontier agent separates once the tree names a foreign origin, and under explicit principal labels it separates at both levels, while UI-TARS separates inline only.</p>')
A('<p class="ni">One caveat belongs with this result. We registered in advance a stronger form of the test, requiring the two rates to agree within ten points on every '
  'act cell individually, and three inline cells did not meet it when it was scored: Qwen3-VL on permission, and both UI-TARS and the frontier agent on update. '
  'That test takes the context as its unit and bootstraps over the two, so its intervals are wider than the point gaps Table V prints. '
  'Two of the three are the persistence effect above; the third is the frontier agent\'s update cell, which carried three episodes per arm when the test was scored. '
  'What the paired test establishes is therefore that no difference is detectable at the moment of decision, at a sample size that resolves a disagreement ratio of about four to one.</p>')
A(table("Every pair counted as a pair, at two outcomes. Agreed counts pairs whose halves behaved alike, whether both acted or neither did; the two disagreement columns carry the result. Read the top two rows against the bottom two. Takeaway: at the first action disagreements are few and run both ways, while over whole episodes they are more frequent and run one way inline only, which Section 6.3 attributes to the application rather than the agent.",
  '<table><thead><tr><th style="width:30%">Outcome</th><th>Surface</th><th>Pairs</th><th>Agreed</th><th>Only the real prompt</th><th>Only the copy</th><th>p</th></tr></thead><tbody>'
  '<tr><td rowspan="2">At the first action<br><span style="color:var(--mut)">inline, the two observations are identical here</span></td><td>inline</td><td>64</td><td>60</td><td>3</td><td>1</td><td>0.625</td></tr><tr><td>framed</td><td>66</td><td>54</td><td>6</td><td>6</td><td>1.000</td></tr><tr><td rowspan="2">Over the whole episode<br><span style="color:var(--mut)">the two runs have diverged by now</span></td><td>inline</td><td>64</td><td>55</td><td>9</td><td>0</td><td>0.0039</td></tr><tr><td>framed</td><td>66</td><td>51</td><td>9</td><td>6</td><td>0.607</td></tr></tbody></table>'))
A(table("Paired disagreements at the moment of decision, by agent and observation. Each cell counts pairs whose halves diverged, as (favouring the application&#8217;s own prompt) : (favouring the copy), with the exact McNemar p. Nothing is excluded on screenshots alone; in the framed tree cell the vendor&#8217;s classifier halted the copy in 24 of 46 pairs and those are left out, which Section 6.7 reports. Read down the first column, then across a row. Takeaway: nothing separates on screenshots at conventional significance, though one framed cell leans toward the copy; separation appears only where the observation names a second principal and only for an agent that reads it.",
  '<table><thead><tr><th style="width:26%">Agent and surface</th><th>Screenshot only</th><th>+ accessibility tree</th><th>+ principal labels</th></tr></thead><tbody>'
  '<tr><td>Qwen3-VL &middot; inline</td><td>0 : 0&nbsp;&nbsp;<span style="color:var(--mut)">p = 1.00</span></td><td>4 : 1&nbsp;&nbsp;<span style="color:var(--mut)">p = 0.38</span></td><td>2 : 1&nbsp;&nbsp;<span style="color:var(--mut)">p = 1.00</span></td></tr><tr><td>Qwen3-VL &middot; framed</td><td>0 : 5&nbsp;&nbsp;<span style="color:var(--mut)">p = 0.06</span></td><td>0 : 1&nbsp;&nbsp;<span style="color:var(--mut)">p = 1.00</span></td><td>0 : 4&nbsp;&nbsp;<span style="color:var(--mut)">p = 0.12</span></td></tr><tr><td>UI-TARS &middot; inline</td><td>2 : 1&nbsp;&nbsp;<span style="color:var(--mut)">p = 1.00</span></td><td>0 : 3&nbsp;&nbsp;<span style="color:var(--mut)">p = 0.25</span></td><td><b>11 : 0</b>&nbsp;&nbsp;<span style="color:var(--mut)">p &lt; 0.001</span></td></tr><tr><td>UI-TARS &middot; framed</td><td>6 : 1&nbsp;&nbsp;<span style="color:var(--mut)">p = 0.12</span></td><td>2 : 3&nbsp;&nbsp;<span style="color:var(--mut)">p = 1.00</span></td><td>1 : 0&nbsp;&nbsp;<span style="color:var(--mut)">p = 1.00</span></td></tr><tr><td>Claude Opus 5.5 &middot; inline</td><td>1 : 0&nbsp;&nbsp;<span style="color:var(--mut)">p = 1.00</span></td><td>0 : 0&nbsp;&nbsp;<span style="color:var(--mut)">p = 1.00</span></td><td><b>29 : 0</b>&nbsp;&nbsp;<span style="color:var(--mut)">p &lt; 0.001</span></td></tr><tr><td>Claude Opus 5.5 &middot; framed</td><td>0 : 0&nbsp;&nbsp;<span style="color:var(--mut)">p = 1.00</span></td><td><b>22 : 0</b>&nbsp;&nbsp;<span style="color:var(--mut)">p &lt; 0.001</span></td><td><b>18 : 0</b>&nbsp;&nbsp;<span style="color:var(--mut)">p &lt; 0.001</span></td></tr></tbody></table>'))
A(figure("clicks", D/"figures/first-clicks.png", CAPTIONS["clicks"]))
A(figure("firstact", D/"figures/first-action.png", CAPTIONS["firstact"]))

A('<h3>6.4&nbsp;&nbsp;Comparison with indirect prompt injection</h3>')
A('<p class="ni">On the same harness, agents and act cells we ran text injections in three hand written templates: a plain imperative, an appeal to authority, and instructions hidden in markup. '
  'The hidden template, the canonical form of indirect prompt injection, never succeeded in 89 episodes against any agent. '
  'The strongest template against Claude Opus 5.5 reached 33 percent; the copy reached 96 percent on the same cells, and exceeded the best injection template for every agent.</p>')
A('<p>The two attacks also move in opposite directions across the three agents, on one context and as an exploratory reading. Injection success does not rise in that order in our record and the hidden variant is uniformly defeated, '
  'which is consistent with the field\'s reported progress. The copy\'s rate rises, though the frontier agent carries that gap: the two open models sit at 71 and 74 percent with intervals that almost coincide. '
  'A defensive programme calibrated on the first trend will report improving security while the second worsens beneath it.</p>')
A(figure("vsinj", D/"figures/23-vs-injection.png", CAPTIONS["vsinj"], span=True))

A('<h3>6.5&nbsp;&nbsp;Screen level and prompt level defences</h3>')
A('<p class="ni">Four defence classes were run over the recorded screens, each on its own sample: a published screenshot screener at its released version, a local vision language model as a judge, the frontier model as a judge, '
  'and a warning in the system prompt. Table VIII gives the first three, which are detectors scored by what they flag. '
  'The warning is scored by whether the agent still acted: with it in place UI-TARS acted on 28 of 36 copies against 26 of 36 genuine prompts, and Qwen3-VL on 30 of 36 against 33 of 36, both intervals covering zero. '
  'No class attains a positive advantage.</p>')
A('<p>Where the renderings are identical the advantage is not small but exactly zero, because a defence reading the same bytes has the same output distribution on both halves. '
  'No threshold or retraining moves a quantity that is constant in its input, which is why we report no sweep of the operating point. '
  'The one estimate away from zero belongs to the frontier judge and points the wrong way: at the framed level it refuses the genuine prompt more often than the copy. Its contribution is cost, not protection.</p>')
A(table("Every defence class on every surface. Advantage is the rate on the copy minus the rate on the genuine prompt, so a defence that separates them is positive. Read the advantage column. Takeaway: every entry is zero or negative and every interval includes zero, and the single negative entry means that defence refuses genuine prompts more often than copies. Each detector was run over its own sample of the recorded screens for that surface, which is why the three counts differ and why all three exceed Table V&#8217;s episode counts: the samples are not restricted to the act cells where an agent cleared the utility floor, and they include the screens behind its greyed rows. A fourth class, a warning in the system prompt, is reported in the text because it measures whether the agent acted rather than what a detector flagged.",
  '<table><thead><tr><th style="width:30%">Defence</th><th>Surface</th><th>Flagged on the real prompt</th><th>Flagged on the copy</th><th>Advantage</th><th>95% interval</th><th>Screens scored</th></tr></thead><tbody>'
  '<tr><td>Screenshot screener</td><td>inline</td><td>0.14</td><td>0.14</td><td><b>0.00</b></td><td>[-0.07, +0.07]</td><td>348</td></tr><tr><td></td><td>framed</td><td>0.23</td><td>0.23</td><td><b>0.00</b></td><td>[-0.08, +0.08]</td><td>408</td></tr><tr><td></td><td>chat</td><td>0.00</td><td>0.00</td><td><b>0.00</b></td><td>[-0.18, +0.18]</td><td>36</td></tr><tr><td>Local vision language judge</td><td>inline</td><td>0.00</td><td>0.00</td><td><b>0.00</b></td><td>[-0.06, +0.06]</td><td>128</td></tr><tr><td></td><td>framed</td><td>0.00</td><td>0.00</td><td><b>0.00</b></td><td>[-0.06, +0.06]</td><td>132</td></tr><tr><td></td><td>chat</td><td>0.00</td><td>0.00</td><td><b>0.00</b></td><td>[-0.18, +0.18]</td><td>36</td></tr><tr><td>Frontier model as judge</td><td>inline</td><td>1.00</td><td>1.00</td><td><b>0.00</b></td><td>[-0.06, +0.06]</td><td>114</td></tr><tr><td></td><td>framed</td><td>0.82</td><td>0.67</td><td><b>-0.14</b></td><td>[-0.29, +0.01]</td><td>118</td></tr><tr><td></td><td>chat</td><td>0.00</td><td>0.00</td><td><b>0.00</b></td><td>[-0.18, +0.18]</td><td>36</td></tr>'
  '</tbody></table>'))

A('<h3>6.6&nbsp;&nbsp;Structured observation: where the floor lifts</h3>')
A('<p class="ni">Consequence C2 predicts that structure helps exactly where it assigns distinct principals, and the record matches. '
  'The accessibility tree changes nothing at the inline level, where it carries one principal for the whole document and the only structural difference is a dialog node the sanitiser strips from content. '
  'At the framed level the adversary\'s frame declares a different origin, and that is the one structural fact an agent was seen to read: the frontier agent separates none of 36 inline pairs and every framed pair whose copy the vendor\'s classifier left intact, 22 of 22. '
  'The classifier halted the copy in the other 24 framed pairs (Section 6.7). Counting each halted copy instead as one the agent would have acted on, the separation falls to 0.33 or below on three of the six framed act cell and context groups, and the result rests on the three that carry no halt. '
  'Neither open weight model reads it at either level.</p>')
A(f'<p class="ni">With an explicit channel labelling each principal, the frontier agent\'s success on the copy falls from 96 to 11 percent while its utility on the genuine prompt stays at 100. '
  'UI-TARS reads the channel too, but only partly and only on one surface: its copy rate falls from 100 to 87 percent and it separates 11 of 11 inline pairs, while on the framed surface it separates one. '
  'Qwen3-VL does not move at all. Its copy rate instead rises one step earlier, where the tree is added, from 62 to 100 percent on the cells measurable in all three arms. '
  'That is the persistence effect of Section 6.3 again rather than a new weakness, because the tree stops this agent navigating away before it engages either half. '
  'That asymmetry is itself a result and it decides the form of the mitigation: '
  'a control whose effect depends on the model electing to read a field protects only models able to read it, which is the wrong direction of dependence for a security control.</p>')
A(figure("dose", D/"figures/dose-response.png", CAPTIONS["dose"]))
A('<h3>6.7&nbsp;&nbsp;A deployed commercial stack</h3>')
A('<p class="ni">The vendor\'s computer use stack scans screenshots returned to the model with an injection classifier and may halt the request; the vendor also documents that it steers the model to confirm instructions found in them. Both are defences against instructions, and the copy carries none. '
  'Two properties of that classifier are measurable from outside, and we report both at the level of an externally observable stop reason, claiming a pattern and not a mechanism.</p>')
A('<p>First, within the paired record every halt fell on an adversary episode and none on the application\'s own prompt, which reads as a working defence until the condition is examined. '
  'The scope matters: in the separate utility floor run, where no copy is present, the same classifier halted all six of this agent\'s credential attempts on the application\'s own prompt. '
  'Within that record halts occur in one request configuration of six: 24 of 110 structured requests at the framed level, none of the 266 elsewhere, so there the filter never fires on screenshots alone, never inline, and never once principal labels are present. '
  'The floor run shows that scope belongs to the record and not to the classifier: its six halts fell on inline and framed credential screens carrying no copy at all. '
  'It is not inert outside them. A probe on 60 single screens with the condition hidden shows it active but not keyed to the attack: it stopped the benign inline screen, which carries no prompt at all, 3 of 3 times, against 13 of 18 for inline prompt screens.</p>')
A(figure("blind", D/"figures/probe-blind.png", CAPTIONS["blind"]))
A(f'<p>Second, that condition is easy to remove. We varied two factors on one recorded screenshot: whether the tree carried principal annotations, and whether a sentence of policy text was appended to the task. '
  f'The annotations did nothing. In this configuration the sentence accounted for the whole effect, {halt_no} of 20 requests halted without it and {halt_yes} of 20 with it, Fisher exact <i>p</i> &lt; 0.0001. '
  'A single sentence of ordinary policy text, the kind a developer adds to make an agent safer, coincided with the filter stopping nothing at all.</p>')

# ───────────────────────────────── VII
A('<h2>7&nbsp;&nbsp;Mitigation: A Trusted Path for Agents</h2>')
A('<p class="ni">C1 rules out a better detector, so the remedy must add information the adversary cannot write: which principal rendered each region. '
  'That is a trusted path, moved from the human to the agent and from presentation to input.</p>')
A('<h3>7.1&nbsp;&nbsp;Two placements, measured</h3>')
A(f'<p class="ni">We evaluated two placements of the same channel. Given to the model it helps only a model that uses it: {SHORT["anthropic_frontier"]} falls to {pc(dose["provenance"]["replica"])[:-1]} percent, UI-TARS moves partly and Qwen3-VL not at all. '
  f'Enforced in the harness it works regardless: a policy admitting an act only when the prompt region\'s principal is entitled refused {pol["replica"]["n"]-pol["replica"]["k"]} of {pol["replica"]["n"]} copies '
  f'and admitted {pol["genuine"]["k"]} of {pol["genuine"]["n"]} genuine prompts, an exact upper bound on the error of {pol["cr_ci"][1]} against a bound of {pol["prereg_bound"]} registered beforehand. The policy is 57 lines of Python.</p>')
A('<p>The bound is met by 0.00006. A single error would have failed it, and asserting it with room to spare would need roughly twice the episodes. '
  'This is also the only claim replicated from a clean run outside the pipeline that produced it, to a byte identical summary, which is replication and not third party reproduction.</p>')
A(figure("fix", D/"figures/the-fix.png", CAPTIONS["fix"]))
A('<p>Two recent defences restore a trust boundary by other means, and our measurements bound where each can work. '
  'SA-CUA separates trusted from untrusted screen regions by rules over the accessibility tree, passing content between two models through an endorsement channel [18]; UCM restores the boundary earlier, masking untrusted regions of the document before the agent observes the page [19]. '
  'Both read the same structure, so both inherit one condition: the document must already mark which regions are untrusted. '
  'Consequence C2 and Section 6.6 say where it does. At the inline level the tree assigns one principal to the whole document, and no rule over it separates the application\'s prompt from a copy in a message body; where content sits in a frame of a distinct origin, the tree carries the fact and a rule over it is sound. '
  'Our result contradicts neither. It states what they require and measures the surface where that requirement is absent.</p>')
A('<h3>7.2&nbsp;&nbsp;The signal already exists below the harness</h3>')
A('<p class="ni">The channel needs no new platform capability. Windows UI Automation exposes a process identity and a dialog flag on every element [21]. macOS draws system credential prompts from a separate user process and exposes window ownership. '
  'Android reports the owning package on every accessibility node, and Chromium builds accessibility trees per frame, linked by frame identity. '
  'The signal exists nearly everywhere an agent operates, and is discarded at one point: the harness captures a raster and sends it, and the vendor interface we inspected at the request level forwards an image and at most a URL, which is what the two others\' documentation says of theirs. '
  'That discard is both the cause and the cheapest place to fix it, because the harness is the last component still holding the information when it is thrown away.</p>')

A('<h3>7.3&nbsp;&nbsp;Deployment guidance</h3>')
A('<p class="ni">Three recommendations follow from the measurements.</p>')
A('<p class="ni">1) <i>Harness vendors.</i> Forward a principal identifier for each region alongside the screenshot, and enforce entitlement in the harness rather than delegating the check to the model. '
  'This is the only configuration measured to remove the attack, and the only one whose effect does not depend on the model.</p>')
A('<p class="ni">2) <i>Application developers.</i> Do not render content written by others in the same document as your own authority prompts. Where the product requires it, render that content in a child frame of a '
  'distinct origin: at the framed level the structure at least carries the fact that could be checked, which is the difference between a defence being hard and being impossible. Thunderbird already does this, and the copy reaches no sink there at all (Section 8).</p>')
A('<p class="ni">3) <i>Operators.</i> Treat coverage by an injection classifier as dependent on configuration until demonstrated otherwise. In the deployed stack we measured, coverage was confined to one request shape '
  'and, in that configuration, was removed by a single sentence appended to the task.</p>')

# ───────────────────────────────── VIII
A('<p><b>Why the deputy framing matters.</b> Treating this as a perception problem invites perception remedies, and Section 6.5 shows what those are worth. '
  'Treating it as an origin validation failure that produces a confused deputy points at the missing control and at the component that should hold it. '
  'That literature has known the remedy since 1988 [1]: do not let the deputy infer authority from ambient context, hand it an unforgeable reference to the authority being invoked.</p>')
A('<h2>8&nbsp;&nbsp;Limitations</h2>')
A('<p class="ni"><b>On the strength of the claim.</b> Our indistinguishability result is an impossibility bound under a measured premise, not an empirical generalisation, and it should be read as constraining the defence '
  'design space rather than as a law about agents. What is empirical is that the premise holds in a realistic rendering context, that four defence classes behave as the bound requires, '
  'and that the attack outperforms the alternative the field is hardening against. '
  'This is a proof of concept: one instrumented application, three agents, two task contexts. It establishes the class and the bound and shows what a screenshot defence cannot do; it does not measure prevalence.</p>')

# ───────────────────────────────── IX
A('<p class="ni"><b>One application, which we built.</b> Ground truth needs sinks we control and a secret only the application can stamp, which no production product provides. '
  'The mechanism does not depend on our application: it depends on content written by others being rendered in the same window as an application\'s own prompts. '
  'We have not driven a shipped product end to end, and that is the most useful thing a later study adds.</p>')
A('<p><b>Not every mail client renders this way.</b> Of the two production clients we measured, Roundcube\'s full view renders the message body inline in its own document; '
  'Thunderbird frames it in a child document and will not submit a form from message content at all. '
  'An agent found the copied credential field there, typed into it and pressed Return three times, and no request left the client. The copy has to be a linked page instead, which is the condition our chat rows measure and where no agent acted on it. '
  'The attack carries on clients that render inline; on one built like Thunderbird it does not.</p>')
A('<p><b>Three agents, one vendor.</b> Two open weight models and one commercial agent, and the attack succeeds on all three. A second vendor\'s agent is the obvious next sample.</p>')
A('<p><b>Small cells.</b> Between three and fifteen episodes per arm per act cell.</p>')
A('<p><b>Detectability, not equivalence.</b> The paired test shows no detectable difference at the decision point. It does not show the two rates are identical, and the stronger per cell form we registered was not met, for the reasons in Section 6.3.</p>')
A('<p><b>Desktop and operating system surfaces.</b> Where the mitigation is cheapest, because window ownership is already available, we piloted them with scripted controls only; no agent ran there, and the operating system prompt cell did not reach a measurable state.</p>')

A('<h2>9&nbsp;&nbsp;Ethics and Responsible Disclosure</h2>')
A('<p class="ni">All experiments ran against an application we built, on hardware we control. No third party service was attacked, no one\'s account was accessed, no real credential was entered anywhere, '
  'and the only commercial system exercised was a vendor\'s computer use interface, used as documented and within its terms.</p>')
A('<p>We publish the construction because it needs no specialised knowledge to rediscover and no capability an adversary lacks. Naming the class precisely, with a measured and deployable mitigation, '
  'is worth more than the marginal uplift to someone who can already post a message. The two findings about the deployed stack are reported at the level of an observable stop reason, '
  'with no claim about classifier internals and no evasion technique beyond the single observation that is itself the finding.</p>')

# ───────────────────────────────── XI
A('<h2>10&nbsp;&nbsp;Conclusion</h2>')
A('<p class="ni">We put three agents to work in an instrumented application and let an attacker do one thing: post a message. The message contained a copy of the application\'s own security prompt.</p>')
A('<p>Every agent answered it. Two were open weight models built for screen control, one was a frontier commercial model running through its vendor\'s interface, '
  'and at the moment each chose what to click, none distinguished the copy from the real thing. That is unsurprising once you know the two arrive as the same image, which we measured rather than assumed.</p>')
A('<p>We then ran the defences that exist. A published screenshot detector, a small model judging the screen, a frontier model judging the screen, and a warning in the agent\'s instructions. '
  'None gained any advantage. Each flagged the fake and the real prompt at the same rate, and the frontier judge rejected real prompts more often than fakes. '
  'We also ran prompt injection against the same agents and surfaces. The copy beat it every time, and the hidden text version never worked.</p>')
A('<p>The attack is crude, and that is exactly the problem. Defences built for clever attacks look for an artefact. This one has none. '
  'It also means a better model does not help: models separate inputs that differ, and these are the same bytes.</p>')
A('<p>The difference only becomes visible when the page says the content came from elsewhere. Inline, where the clients we measured put messages, it does not. '
  'In a separate origin it does, and only the strongest agent noticed. Labelling each region explicitly fixed that agent and did little for the others. '
  'Enforcing the rule in the harness fixed it for all of them.</p>')
A('<p>Before deploying an agent into an application that renders content from other people, assume that anything drawn in the same window as your own prompts can imitate them. '
  'Keep untrusted content in a separate origin, so the structure at least records where it came from. Do not treat a detector as a control. '
  'The control belongs in the pipeline that feeds the model, not in the model.</p>')

A('<h2>References</h2>')
REFS = [
 'N. Hardy, "The Confused Deputy (or why capabilities might have been invented)," <i>ACM SIGOPS Operating Systems Review</i>, vol. 22, no. 4, pp. 36&ndash;38, 1988.',
 'US Department of Defense, <i>Trusted Computer System Evaluation Criteria</i>, DoD 5200.28-STD, 1985.',
 'C. Jackson, D. R. Simon, D. S. Tan and A. Barth, "An Evaluation of Extended Validation and Picture-in-Picture Phishing Attacks," in <i>Financial Cryptography and Data Security</i>, 2007.',
 'G. Rydstedt, E. Bursztein, D. Boneh and C. Jackson, "Busting Frame Busting: a Study of Clickjacking Vulnerabilities on Popular Sites," in <i>IEEE Web 2.0 Security and Privacy (W2SP)</i>, 2010.',
 'MITRE, "CWE-346: Origin Validation Error," "CWE-441: Unintended Proxy or Intermediary (Confused Deputy)," and "CWE-451: User Interface (UI) Misrepresentation of Critical Information," Common Weakness Enumeration.',
 'MITRE, <i>ATLAS</i> (Adversarial Threat Landscape for Artificial-Intelligence Systems), atlas-data distribution, accessed October 2026, and <i>ATT&amp;CK</i> for Enterprise.',
 'K. Greshake, S. Abdelnabi, S. Mishra, C. Endres, T. Holz and M. Fritz, "Not What You\'ve Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection," in <i>ACM Workshop on Artificial Intelligence and Security (AISec)</i>, 2023.',
 'Y. Zhang, T. Yu and D. Yang, "Attacking Vision-Language Computer Agents via Pop-ups," in <i>Proc. 63rd Annual Meeting of the Association for Computational Linguistics (ACL)</i>, pp. 8387&ndash;8401, 2025.',
 'E. Debenedetti, J. Zhang, M. Balunovi&#263;, L. Beurer-Kellner, M. Fischer and F. Tram&egrave;r, "AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents," in <i>NeurIPS Datasets and Benchmarks Track</i>, 2024.',
 'T. Cao, B. Lim, Y. Liu, Y. Sui <i>et al.</i>, "VPI-Bench: Visual Prompt Injection Attacks for Computer-Use Agents," arXiv:2506.02456, 2025.',
 'Y. Zhang, X. Li, L. Cai and J. Li, "Environmental Injection Attacks against GUI Agents in Realistic Dynamic Environments," arXiv:2509.11250, 2025.',
 'Z. Liu, H. Sun, Z. Fu, X. Duan <i>et al.</i>, "AgentHijack: Visual Patch Attacks on Multimodal Computer-Use Agents," arXiv:2609.09212, 2026.',
 'D. Jones, G. Severi, M. Pouliot, G. Lopez <i>et al.</i>, "A Systematization of Security Vulnerabilities in Computer Use Agents," arXiv:2507.05445, 2025.',
 'W. Xu, "Temporal UI State Inconsistency in Desktop GUI Agents: Formalizing and Defending Against TOCTOU Attacks on Computer-Use Agents," arXiv:2604.18860, 2026.',
 'L. Wu, C. Wang, T. Liu, Y. Zhao <i>et al.</i>, "From Assistants to Adversaries: Exploring the Security Risks of Mobile LLM Agents," arXiv:2505.12981, 2025.',
 'Y. Luo, H. Zhu, S. Pang, Z. Lu <i>et al.</i>, "AgentRAE: Remote Action Execution through Notification-based Visual Backdoors against Screenshots-based Mobile GUI Agents," arXiv:2603.23007, 2026.',
 'X. Liu, B. He, X. Liu, A. Luo, H. Zhang <i>et al.</i>, "Visual Confused Deputy: Exploiting and Defending Perception Failures in Computer-Using Agents," arXiv:2603.14707, 2026.',
 'D. Seip, B. Markovinovi&#263; and M. Hein, "Towards Safe Autonomy for Computer Use," arXiv:2610.18508, 2026.',
 'K. Nikoli&#263;, E. Zverev, J. Rando, M. Jagielski, E. Debenedetti and F. Tram&egrave;r, "Untrusted Content Masking for Web Agents with Security Guarantees," arXiv:2607.05277, 2026.',
 'M. Du, H. Fang, H. Ma, J. Chen, K. Xu <i>et al.</i>, "SnapGuard: Lightweight Prompt Injection Detection for Screenshot-Based Web Agents," arXiv:2604.25562, 2026.',
 'Microsoft, "UI Automation Properties Overview"; Apple, "Security Architecture" and <code>CGWindowListCopyWindowInfo</code>; Android, <code>AccessibilityNodeInfo</code> reference; The Chromium Projects, accessibility documentation.',
 'Anthropic, computer use tool documentation, dated toolset <code>computer_toolset_20260801</code>.',
]
for i, r in enumerate(REFS, 1):
    A(f'<p class="ref">[{i}] {r}</p>')

# ───────────────────────────────── appendices
A('</div></div>')

html = "\n".join(P)
import re as _re
html = _re.sub(r'(<div class="svgwrap">.*?</svg></div>)\s*(?=<figcaption)', r'\1', html, flags=_re.S)
OUT = D / "doppelganger-screens.html"
OUT.write_text(html, encoding="utf-8")
print("paper written:", OUT, f"{len(html):,} bytes")
print("figures:", _counter[0], "tables:", _tbl[0])
import re
txt = re.sub(r"<[^>]+>", " ", re.sub(r'data:image/[a-z]+;base64,[A-Za-z0-9+/=]+', '', html))
print("words:", len(txt.split()))
