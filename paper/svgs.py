SVG_TRUST = """<div class="svgwrap"><svg viewBox="0 0 980 308" role="img" aria-label="Trust boundaries: what the attacker controls and what the agent sees">
<defs><marker id="ar" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#52514e"/></marker></defs>
<g font-family="DejaVu Sans, sans-serif" font-size="12" fill="#0b0b0b">
<rect x="14" y="30" width="330" height="240" rx="5" fill="#fff" stroke="#dedcd6"/>
<text x="26" y="50" font-size="11.5" fill="#52514e" letter-spacing="1">THE APPLICATION (app.example)</text>
<rect x="30" y="64" width="298" height="52" rx="4" fill="#eaf2fd" stroke="#2a78d6"/>
<text x="42" y="84" font-weight="600">Its own prompt</text><text x="42" y="101" font-size="11" fill="#52514e">stamped with a per-run secret only its script reads</text>
<rect x="30" y="130" width="298" height="124" rx="4" fill="#fdf0e9" stroke="#eb6834" stroke-dasharray="5 3"/>
<text x="42" y="150" font-size="11.5" fill="#b4532a" letter-spacing="1">ATTACKER-WRITTEN REGION</text>
<text x="42" y="168" font-size="11" fill="#52514e">a message body the application renders</text>
<rect x="42" y="178" width="274" height="62" rx="3" fill="#fff" stroke="#eb6834"/>
<text x="54" y="198" font-weight="600">A copy of that prompt</text>
<text x="54" y="215" font-size="11" fill="#52514e">same pixels · form points at the attacker</text>
<text x="54" y="231" font-size="11" fill="#52514e">no instruction to the model anywhere in it</text>
<rect x="390" y="86" width="190" height="128" rx="5" fill="#fff" stroke="#dedcd6"/>
<text x="402" y="106" font-size="11.5" fill="#52514e" letter-spacing="1">THE HARNESS</text>
<text x="402" y="128" font-weight="600">one screenshot</text>
<text x="402" y="146" font-size="11" fill="#52514e">(and at most a URL)</text>
<text x="402" y="172" font-size="11" fill="#b4532a">no frame origin</text>
<text x="402" y="188" font-size="11" fill="#b4532a">no window owner</text>
<text x="402" y="204" font-size="11" fill="#b4532a">no process identity</text>
<rect x="626" y="86" width="150" height="128" rx="5" fill="#fff" stroke="#dedcd6"/>
<text x="638" y="106" font-size="11.5" fill="#52514e" letter-spacing="1">THE MODEL</text>
<text x="638" y="132" font-size="11" fill="#52514e">sees two regions</text>
<text x="638" y="150" font-size="11" fill="#52514e">that are the same</text>
<text x="638" y="168" font-size="11" fill="#52514e">bytes, and is asked</text>
<text x="638" y="186" font-size="11" fill="#52514e">to finish the task</text>
<rect x="822" y="86" width="144" height="128" rx="5" fill="#fff" stroke="#dedcd6"/>
<text x="834" y="106" font-size="11.5" fill="#52514e" letter-spacing="1">THE SINK</text>
<text x="834" y="132" font-size="11" fill="#52514e">credentials,</text><text x="834" y="150" font-size="11" fill="#52514e">a permission,</text>
<text x="834" y="168" font-size="11" fill="#52514e">a payment — to</text><text x="834" y="186" font-size="11" fill="#b4532a">whoever drew it</text>
<line x1="346" y1="150" x2="386" y2="150" stroke="#52514e" marker-end="url(#ar)"/>
<line x1="582" y1="150" x2="622" y2="150" stroke="#52514e" marker-end="url(#ar)"/>
<line x1="778" y1="150" x2="818" y2="150" stroke="#52514e" marker-end="url(#ar)"/>
<text x="490" y="290" text-anchor="middle" font-size="11" fill="#8a8984">the dashed region is everything the adversary controls: content, and nothing else</text>
<text x="490" y="20" text-anchor="middle" font-size="11.5" fill="#52514e">origin information is discarded here, once, and never recovered downstream</text>
</g></svg></div>"""

SVG_CHAIN = """<div class="svgwrap"><svg viewBox="0 0 980 190" role="img" aria-label="Kill chain of a screen forgery">
<defs><marker id="ar2" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#8a8984"/></marker></defs>
<g font-family="DejaVu Sans, sans-serif" font-size="11.5" fill="#0b0b0b">
<!--stages-->
<g>
<rect x="8" y="34" width="176" height="92" rx="4" fill="#fff" stroke="#dedcd6"/>
<text x="20" y="54" font-weight="600">1 · Delivery</text>
<text x="20" y="73" font-size="10.6" fill="#52514e">the adversary posts a</text><text x="20" y="88" font-size="10.6" fill="#52514e">message, ticket or</text>
<text x="20" y="103" font-size="10.6" fill="#52514e">shared page</text>
<text x="20" y="120" font-size="9.8" fill="#2a78d6">ATT&amp;CK T1566</text>
</g><g>
<rect x="206" y="34" width="176" height="92" rx="4" fill="#fff" stroke="#dedcd6"/>
<text x="218" y="54" font-weight="600">2 · Staging</text>
<text x="218" y="73" font-size="10.6" fill="#52514e">the application renders</text><text x="218" y="88" font-size="10.6" fill="#52514e">it, drawing a copy of</text>
<text x="218" y="103" font-size="10.6" fill="#52514e">its own prompt</text>
<text x="218" y="120" font-size="9.8" fill="#2a78d6">ATT&amp;CK T1036 · masquerading</text>
</g><g>
<rect x="404" y="34" width="176" height="92" rx="4" fill="#fff" stroke="#dedcd6"/>
<text x="416" y="54" font-weight="600">3 · Trigger</text>
<text x="416" y="73" font-size="10.6" fill="#52514e">the user gives the agent</text><text x="416" y="88" font-size="10.6" fill="#52514e">an ordinary task; no</text>
<text x="416" y="103" font-size="10.6" fill="#52514e">lure is needed</text>
<text x="416" y="120" font-size="9.8" fill="#2a78d6">ATLAS AML.T0051</text>
</g><g>
<rect x="602" y="34" width="176" height="92" rx="4" fill="#fdf0e9" stroke="#eb6834"/>
<text x="614" y="54" font-weight="600">4 · Execution</text>
<text x="614" y="73" font-size="10.6" fill="#52514e">the agent screenshots,</text><text x="614" y="88" font-size="10.6" fill="#52514e">sees the prompt and</text>
<text x="614" y="103" font-size="10.6" fill="#52514e">answers it</text>
<text x="614" y="120" font-size="9.8" fill="#b4532a">no instruction is read</text>
</g><g>
<rect x="800" y="34" width="172" height="92" rx="4" fill="#fff" stroke="#dedcd6"/>
<text x="812" y="54" font-weight="600">5 · Impact</text>
<text x="812" y="73" font-size="10.6" fill="#52514e">credentials, a scope</text><text x="812" y="88" font-size="10.6" fill="#52514e">grant or a payment</text>
<text x="812" y="103" font-size="10.6" fill="#52514e">reach the adversary</text>
<text x="812" y="120" font-size="9.8" fill="#2a78d6">T1056 · T1528 · T1078</text>
</g>
<line x1="186" y1="80" x2="202" y2="80" stroke="#8a8984" marker-end="url(#ar2)"/>
<line x1="384" y1="80" x2="400" y2="80" stroke="#8a8984" marker-end="url(#ar2)"/>
<line x1="582" y1="80" x2="598" y2="80" stroke="#8a8984" marker-end="url(#ar2)"/>
<line x1="780" y1="80" x2="796" y2="80" stroke="#8a8984" marker-end="url(#ar2)"/>
<text x="490" y="20" text-anchor="middle" font-size="11" fill="#52514e">Every stage uses a capability the adversary already has. Nothing in the chain requires a model to be jailbroken.</text>
<text x="490" y="160" text-anchor="middle" font-size="11" fill="#8a8984">Detection-based defences sit at stage 4 and look for an instruction. There is none to find.</text>
</g></svg></div>"""

SVG_LADDER = """<div class="svgwrap"><svg viewBox="0 0 980 212" role="img" aria-label="How much origin information each observation carries">
<g font-family="DejaVu Sans, sans-serif" font-size="11.5" fill="#0b0b0b">
<rect x="10" y="26" width="228" height="140" rx="4" fill="#fdf0e9" stroke="#eb6834"/>
<text x="124" y="48" text-anchor="middle" font-weight="600">L0 · pixels only</text>
<text x="124" y="70" text-anchor="middle" font-size="10.8" fill="#52514e">what every shipped harness sends</text>
<text x="124" y="92" text-anchor="middle" font-size="10.8" fill="#52514e">copy and original: one image</text>
<text x="124" y="120" text-anchor="middle" font-size="11" fill="#b4532a">measured: no defence helps</text>
<text x="124" y="140" text-anchor="middle" font-size="11" fill="#b4532a">and none can (Section IV)</text>
<rect x="252" y="26" width="228" height="140" rx="4" fill="#fdf0e9" stroke="#eb6834"/>
<text x="366" y="48" text-anchor="middle" font-weight="600">L1 · inline structure</text>
<text x="366" y="70" text-anchor="middle" font-size="10.8" fill="#52514e">a tree with one principal in it</text>
<text x="366" y="92" text-anchor="middle" font-size="10.8" fill="#52514e">role attributes are attacker-writable</text>
<text x="366" y="120" text-anchor="middle" font-size="11" fill="#b4532a">measured: no agent separates</text>
<text x="366" y="140" text-anchor="middle" font-size="11" fill="#52514e">webmail, chat and ticketing live here</text>
<rect x="494" y="26" width="228" height="140" rx="4" fill="#eaf2fd" stroke="#2a78d6"/>
<text x="608" y="48" text-anchor="middle" font-weight="600">L2 · frame origin</text>
<text x="608" y="70" text-anchor="middle" font-size="10.8" fill="#52514e">the tree names a child frame's origin</text>
<text x="608" y="92" text-anchor="middle" font-size="10.8" fill="#52514e">the first visible provenance</text>
<text x="608" y="120" text-anchor="middle" font-size="11" fill="#1c5cab">the frontier agent separates here</text>
<text x="608" y="140" text-anchor="middle" font-size="11" fill="#b4532a">the open models ignore it</text>
<rect x="736" y="26" width="234" height="140" rx="4" fill="#e9f6f0" stroke="#1baf7a"/>
<text x="853" y="48" text-anchor="middle" font-weight="600">L3 · a provenance channel</text>
<text x="853" y="70" text-anchor="middle" font-size="10.8" fill="#52514e">who drew each region, by name</text>
<text x="853" y="92" text-anchor="middle" font-size="10.8" fill="#52514e">unwritable from inside content</text>
<text x="853" y="120" text-anchor="middle" font-size="11" fill="#14805a">a policy here refuses every copy</text>
<text x="853" y="140" text-anchor="middle" font-size="11" fill="#52514e">operating systems already have it</text>
<text x="490" y="190" text-anchor="middle" font-size="11" fill="#8a8984">information about who drew the screen, increasing left to right — agents are deployed at the far left</text>
</g></svg></div>"""