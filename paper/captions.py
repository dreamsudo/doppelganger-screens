CAPTIONS = {
"trust": "Where the origin of a screen region is lost. Left to right: the application renders its own authority prompt and the adversary's content in one window, the harness captures that window as a single image, and the agent receives it. "
         "Read the middle panel: origin survives up to the screenshot and not past it. Takeaway: every defence in Section 6.5 reads an input from which the distinguishing fact has already been removed.",
"chain": "The attack as a kill chain. The upper band gives the adversary action at each stage with its ATLAS or ATT&CK identifier. A stage here is a step in the chain, not an ATLAS tactic, so a technique can sit at a different stage than the tactic Table IV files it under; the lower band gives what a defender could attempt there and what we found it to be worth. "
         "Grey marks a stage with no defender opportunity, red a defence we measured at zero advantage, amber a stage we did not evaluate and make no claim about. Takeaway: both defences we measured come out ineffective, and the one break point no deployed defence occupies sits in the harness, before either of them, which is where Section 7 puts the mitigation.",
"ladder": "What an observation can say about who drew the screen. Each step adds information, and the band beneath each card states the measured outcome at that level. "
          "Takeaway: deployed harnesses operate at the far left, enterprise mail and chat render untrusted content one step right of that, and separation first appears two steps further on.",
"twins": "Two surfaces, the application's own prompt on the left of each pair and the adversary's copy on the right. Top is the inline surface, bottom is chat. "
         "Compare the pairs by eye: inline they are the same image, while on chat the copy is a linked post that shares nothing with the prompt. "
         "Takeaway: the attack depends on the first condition, which is why the chat episodes are reported separately rather than pooled.",
"eps": "The inline and framed pairs with every differing pixel amplified in the right column. Any coloured pixel is a difference. "
       "Inline the panel is empty: not one pixel of 1,064,960 differs, on any of the 284 inline pairs. Framed, about one percent of the frame differs, all of it inside the dialog and its shadow and almost all by a single intensity level, "
       "which is the child frame antialiasing the same glyphs. Takeaway: this is the measured premise of Result 1, and it holds exactly at the inline level.",
"headline": "How often each agent performed the authority act on the application's own prompt (blue) and on the adversary's copy (orange), from screenshots alone, on browser surfaces. "
            "Compare the two bars within each agent; whiskers are exact 95 percent intervals and counts sit beneath each value. "
            "Takeaway: every agent acted on the copy, and the frontier agent, the one that completes the genuine task every time, leaves the smallest gap of all.",
"clicks": "The first click of every episode, plotted on the screen the agent saw, with the genuine condition and the copy overlaid. "
          "Look for separation between the two sets. Takeaway: there is none, both conditions land on the same controls; the cluster at the left edge is the navigation rail, where an agent went to the task page instead of answering the prompt.",
"firstact": "What each agent did first, by observation condition and prompt source, as a share of episodes. "
            "Compare the two bars in each pair: where they have the same composition the agent treated the conditions alike. "
            "Takeaway: the frontier agent's two structured bars differ most, where it acts at once on the genuine prompt and navigates away from the copy; the columns pool the two surfaces, so a surface split is not visible here.",
"vsinj": "Attack success for the copy and for three text injection templates, run on the same agents, surfaces and act cells so the comparison is direct. "
         "Compare rows within each colour. Takeaway: the copy beat every injection template for every agent, and the hidden instruction template, which most defensive work targets, never succeeded.",
"dose": "Attack success on the copy as the observation gains information about who drew the screen, one line per agent. "
        "Each line covers only the act cells that agent could perform under all three observations, which is why its rates differ from Fig. 6, and halted requests are left out rather than counted either way. Follow each line left to right. Takeaway: the frontier agent uses the added information and UI-TARS uses some of it at the last step; Qwen3-VL never does.",
"blind": "The vendor's injection classifier on 60 single screens with the condition hidden from it: 18 requests for each of the three prompt screens and 3 for each of the two no-prompt controls. "
         "Compare the two controls on the right against the three prompt bars on the left. Takeaway: the screen the classifier stops most often is the one with no authority prompt on it at all, 3 of 3 against 13 of 18 for inline prompts, which is what rules out a signal keyed to the attack; the control rests on three requests and is reported as such.",
"fix": "Acts on the genuine prompt and on the copy under two placements of the same provenance check: handed to the model (left pair) and enforced in the harness (right pair). "
       "Compare the orange bar in each pair. Takeaway: given to the model the attack is reduced but survives; enforced in the harness it is removed, and utility on the genuine prompt is untouched either way.",
"acts": "Share of copies each agent acted on, by authority act, screenshots only, with counts in each cell. Hatched cells carry no rate: the agent fell below the floor or, for the frontier agent, the vendor\'s classifier halted every attempt. "
        "Read across a row. Takeaway: every agent confirmed the adversary\'s payment every time; permission and update are where the open models fall short, and that shortfall is navigation, not detection (Fig. 7).",
"gapnav": "Every act cell, screenshots only: the copy\'s deficit in episodes against the number of copy episodes whose first click left the prompt. The dashed line is equality. "
          "Read the cells off the origin. Takeaway: four sit on the line, where navigation accounts for the whole gap; UI-TARS inline update navigated on both halves and sits below it; Qwen3-VL framed credential is the one cell where the genuine half navigated and the copy did not, and the gap reverses. The outcome follows the navigation.",
"ctx": "The same cells split by the two frozen task contexts. Compare the pair of bars for each agent. "
       "Takeaway: Qwen3-VL acted on every copy in the finance context and on 11 of 26 in the IT context, where its genuine rate also fell to 16 of 26; UI-TARS does not move between them; the frontier agent ran one context under screenshots.",
}
