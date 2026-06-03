# Thesis Spine

The single document that defines what this thesis is about and what it commits to.
If anything in this document changes, it is a deliberate event, not a drift.

---

## One sentence

Counterexamples in statistical-specification program synthesis are
discriminative, not absolute; their selection, structure, and cardinality
form a design space that governs what an LLM-guided refinement loop can
learn and how it generalizes.

---

## One paragraph

Classical counterexample-guided inductive synthesis assumes a formal
specification: a counterexample is an input that provably violates it.
Automated heuristic design has no such specification, only a distribution
over instances and a scalar objective. This thesis argues that
counterexamples in this setting are inherently comparative — an instance
is a counterexample only relative to a reference heuristic, and its value
as a learning signal depends on how much it discriminates between a
candidate and a reference. Within this framing, an LLM-guided improvement
loop is a comparative counterexample engine whose behavior is governed by
three choices: which counterexamples are selected, how richly each one is
structured, and how many are used. The thesis characterizes these three
axes empirically, on a single domain (online bin packing) and on top of a
fixed baseline search procedure (EoH), in order to derive design
principles about when, and why, comparative counterexample learning
succeeds or fails.

---

## Three claims to defend

**1. Definitional claim.**
The right counterexample object for statistical-specification synthesis
is the tuple `(instance, candidate, reference, per-instance gap, optional
trace slice, optional diagnosis)`. This object admits a design space —
selection strategy, structural enrichment, cardinality — that the
existing AHD literature has not systematically explored.

**2. Empirical claim.**
Within this design space, selection and structural enrichment
produce the most substantial and interpretable differences in
refinement behavior across the axes this thesis varies. These
differences include shifts in variance profile, tail shape, and
compound-improvement trajectory behavior (Chapter 5), and —
hypothetically for Chapter 6 — shifts in the prevalence of
argmax-equivalent proposals. The framing follows
`statements.md`'s "most substantial and interpretable
differences" language rather than a "dominates" framing; the
thesis does not directly ablate against prompt wording or model
choice, so a dominance claim would overreach.

**3. Generalization claim.**
Comparative counterexample learning exhibits a characteristic
overfitting mode that scales with counterexample set size and with
overlap between the evidence-providing set and the evaluation set. This
mode is predictable, empirically characterizable, and mitigated by a
specific methodological discipline: separating evidence-providing,
step-selecting, and train-gating subsets within the training split.

---

## Locked architectural commitments

These four decisions are load-bearing for the entire thesis. They cannot
be revisited without an explicit conversation in which they are unlocked.

1. **Post-hoc on EoH.** All thesis work operates on EoH's final
   population as a frozen input. EoH itself is an upstream black box and
   is never modified.

2. **Single empirical incumbent.** `h_eoh` — the fitness-best
   member of EoH's final population — is the sole incumbent for
   chapters 5, 6, and 7. The reference is drawn from EoH's final
   population minus the incumbent, after the diversity filter
   defined in chapter 4.

3. **Single testbed.** bp_online is the sole problem domain. Multi-
   problem generalization is named as future work, not attempted.

4. **Single primary model.** Gemini 2.5 Pro at
   `reasoning_effort=medium`, `max_output_tokens=32768`,
   `temperature=1.0` is fixed for the entire thesis to avoid model
   choice as a confounder. This commitment was revised from the
   originally planned Gemini 3.1 Pro Preview (decisions log
   2026-04-21) due to infrastructure constraints. Llama 3.3 70B on
   Groq is the documented backup for reproducibility checks only.

---

## What this thesis does not claim

To prevent scope drift, explicit non-goals:

- This thesis does not propose a new search algorithm to replace EoH.
- This thesis does not claim cross-domain generality from bp_online
  alone; it relocates the generality claim to the architecture, not the
  trace vocabulary.
- This thesis does not claim to outperform all existing reflective AHD
  systems; it isolates and studies one well-defined mechanism.
- This thesis does not include training-based or RL-based approaches.
