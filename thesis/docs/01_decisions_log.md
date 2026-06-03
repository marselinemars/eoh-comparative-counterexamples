# Decisions Log

Append-only. Newest entries at top. Every locked architectural,
methodological, or scoping decision goes here, with date, brief reason,
and what alternatives were considered.

Format:
**YYYY-MM-DD — short title.** Decision. Reason. Alternatives considered.

---

**2026-05-24 — Session 4 (examiner-convergence sprint) scope locked: 20 items across 7 phases addressing two independent examination reports.**

Decision. Session 4 addresses 20 items raised by two
independent post-session-3 examination agent reports.
Six items appear in both reports (scope honesty, n=3
sample size, argmax-equivalence framing, sign conventions,
OOD scope, Arabic abstract). Each examination adds
unique items (claim-strength table, reproducibility
checklist, statistical analysis plan, reference-selection
justification, novelty paragraph, engineering
interpretation, preliminary-repair reframing,
contribution boundary statement).

Three items are explicitly out of scope:

- Adding actual external baselines (would require a new
  experimental campaign; named in §5.5.8 future work).
- Full H1/H2/H3 hypothesis restructure (incompatible
  with session-1 scope-honesty framing).
- Mathematical formalization in Chapter 2 prose (already
  covered by Appendix D from session 3).

Reason. The two examination reports converge on the most
defense-critical issues (scope honesty, sample-size
language, argmax-equivalence framing) and add unique
items that strengthen the defense surface (claim-strength
table, statistical analysis plan, reference-selection
justification). Addressing 20 items in a single sprint is
feasible because most are small surgical edits (Phase A),
table additions (Phase C), or focused prose additions
(Phase D).

Alternatives considered and rejected.

- Address only convergent items + claim-strength table
  (10-12 items): rejected because the unique items from
  each examination are also defensively valuable, and the
  marginal cost of including them is low given the sprint
  structure.
- Skip session 4 entirely (defense rehearsal next):
  rejected because the examination reports surface real
  gaps that defense rehearsal cannot fix.
- Add actual external baselines (Ex1 Major 2, Ex2 #2):
  rejected as new experimental campaign; named as future
  work.

Reference.

- `thesis/docs/12_session4_plan.md` (this commit)
- `examination_one.docx` (user's records)
- `examination_two.docx` (user's records)
- `thesis/docs/11_session3_plan.md` (prior session's plan)

---

**2026-05-23 — Session 3 (defense-hardening sprint) scope locked: 8 workstreams addressing 8 supervisor-deferred or partially-addressed items, plus a defensive formal-notation appendix.**

Decision. After session 2 closeout, an audit of
deferred supervisor comments identified 8 items worth
revisiting before docx re-export and defense. Session 3
addresses these:

- W-D.3: §4.5.4.1 trajectory plot (one figure
  visualizing the n=6 extension trajectories).
- W-D.1: §1.5 broader LLM-AHD comparison table.
- W-D.2: §1.7 ML-theory structural-similarity
  paragraph.
- W-D.4: Notation glossary appendix.
- W-D.8: Formal-notation appendix (defensive variant
  of supervisor #5/#9; formal notation in appendix,
  not in Chapter 2 prose).
- W-D.5: Chapter 2 §§2.2-2.4 consolidation.
- W-D.6: Structural-redundancy sweep.
- W-D.7: Selective caption rewriting.

Reason. The session-2 closeout audit identified items
where additional work would meaningfully strengthen
defense without conflicting with editorial choices made
in sessions 1 and 2. The eight items selected are those
where the value/risk ratio justifies inclusion; five
other supervisor items remain skipped (full H1/H2/H3
restructure; mathematical formalization in Chapter 2
prose; Figure 2.1 and 2.4 redesigns; additional
trajectory/variance plots beyond W-D.3's one figure).

Alternatives considered and rejected.

- Skip session 3 and move directly to docx re-export.
  Rejected because the audit identified concrete
  defense-strengthening opportunities at acceptable
  cost.
- Address all 13 deferred supervisor items. Rejected —
  five items either conflict with sprint choices or
  are figure-engineering work with low
  defense-readiness return per unit effort.

Reference.

- `thesis/docs/11_session3_plan.md` (this commit).
- `thesis/docs/09_sprint_retrospective.md` (the
  session-1+2 retrospective).
- `review_selmani_hamza.pdf` (supervisor's records).

---

**2026-05-23 — Session 2 (supervisor-response sprint) scope locked: 9 workstreams addressing 9 of 28 supervisor comments.**

Decision. Session 2 addresses nine of the supervisor's
comments via focused additions and one new limitations
subsection. Six supervisor comments are explicitly
skipped because they conflict with session-1 editorial
choices (scope-honesty framing, simplification away from
heavy theoretical notation, content additions rather
than length reduction). Six other supervisor comments
are deferred as figure-heavy or larger-scope work to be
revisited post-defense if time permits. Six supervisor
comments are already addressed by session 1 and require
no further action.

Reason. The session-1 sprint moved the verdict from
"major revisions" toward "minor revisions" by adopting
scope-honest framing and adding substantive empirical
work (E1+E2 Regime B, E4 baselines, E5 trajectory
extension, robustness analyses, statistical
transparency). Several supervisor comments — written
before session 1 ran — pre-date these additions; for
those, session 1's work is the substantive answer. The
session-2 plan focuses on the supervisor comments that
remain applicable and tractable as focused additions
without reversing session-1 editorial choices.

Alternatives considered and rejected.

- Address all 28 supervisor comments. Rejected because
  several conflict directly with session-1 choices;
  addressing them would re-open the examiner-response
  critique session 1 closed.
- Address only the three highest-priority items (CEGIS
  table, budget table, LLM limitations). Rejected — the
  nine-item scope is still tractable and produces a more
  complete supervisor response.
- Defer all supervisor work to post-defense. Rejected —
  the supervisor reviewed the thesis and flagged
  tractable improvements; addressing them before defense
  strengthens the defense.

Reference.

- `thesis/docs/10_session2_plan.md` (this commit).
- `review_selmani_hamza.pdf` (user's records).
- Sprint retrospective (post-session-1 doc the user
  produced).

---

**2026-05-23 — Authoritative source for the thesis text is `thesis/writing/thesis_main.md`; pre-simplification chapter sources archived.**

Decision. The compiled and simplified thesis manuscript
(provided by the user as `thesis_main.md`, ~22.3k words,
1608 lines) supersedes the original chapter sources
(`chapter1_draft.md`, `chapter5.md`, `chapter6.md`,
`chapter7.md`) as the authoritative source for the thesis
text. The pre-simplification sources are moved to
`thesis/writing/_archive_pre_simplification/` as historical
reference, read-only for Phase C purposes. All Phase C
drafts and the final docx re-export target `thesis_main.md`.

Reason. The original chapter sources reflect an earlier
writing phase that was deliberately compressed and
simplified into the current docx ("Thesis Chaps  (2) -
caption-ready.docx"). The compiled docx is what the examiner
reads. The .md equivalent of the docx (`thesis_main.md`) is
what Phase C drafts should target so that the integration
commit produces a thesis the examiner sees. Without this
pivot, all Phase C drafts targeting the original chapter
sources would land in files the examiner does not read.

Consequence: `chapter4_tables_update.md` (commit `9d48eab`)
was authored against `chapter5.md` and `chapter7.md` line
numbers and table identifiers; it needs re-targeting against
`thesis_main.md` in a follow-up commit. The other three
Phase C drafts (`chapter4_section4_5.md`,
`chapter3_section3_3_update.md`,
`chapter1_section1_9_reframe.md`) reference content by
section number rather than by file or line, so they remain
compatible with `thesis_main.md` without changes.

Alternatives considered and rejected.

- Continue working against the original chapter sources,
  then manually port everything to the docx at integration.
  Rejected because Phase C has six more writing workstreams
  (W-ABS, W-INTRO, W-CH5, W-CH6, W-LIMS, W-FINAL) and each
  would need retroactive porting; that's substantially more
  work than the up-front pivot.
- Extract the docx to clean markdown via `zipfile` + XML
  parse. Considered; rejected when the user offered to
  provide the .md directly, which is cleaner (no extraction
  transformation, no formatting loss).
- Delete the pre-simplification sources outright. Rejected
  because decisions-log entries and design docs reference
  them by line; deletion would break those references.

Reference.

- `thesis/writing/thesis_main.md` (this commit).
- `thesis/writing/_archive_pre_simplification/ARCHIVE_README.md`
  (this commit).

---

**2026-05-23 — Phase B outcome regime locked: Regime B (code-matters) for E1+E2 decomposition; Regime α (agree) for E5 n=6 consolidation.**

Decision. Per
`thesis/writing/chapter4_comparative_decomposition_design.md`
§7.2 (Regime B criterion), the empirical evidence places the
comparative-content decomposition in Regime B: showing the
reference's source code is load-bearing for proposal quality;
the gap scalar alone does not recover the lost performance.
Per
`thesis/writing/chapter4_extra_trajectories_design.md` §6.1
(Regime α criterion), the n=6 extension corroborates the n=3
rankings without rank inversion. The Phase C prose templates
from §7.2 of the E1+E2 design doc are now active.

Reason. The matched-pair CIs are:

- Full vs gap-only: mean +207.95, 95% CI [+85.25, +351.97] —
  excludes zero on the positive side (gap-only is worse than
  full).
- Gap-only vs no-reference: mean +78.63, 95% CI [−116.62,
  +279.66] — overlaps zero (cannot statistically distinguish
  gap-only from no-reference at this sample size).
- Full vs no-reference: mean +296.94, 95% CI [+150.78,
  +463.24] — excludes zero on the positive side (no-reference
  is worse than full).

This pattern matches Regime B's pre-specified criterion
exactly (full > gap-only ≈ no-reference).

For E5 n=6: both load-bearing pairs (strat vs wpb at L1 k=4;
strat vs wo1 at L2 k=1) preserve their n=3 direction at n=6
with non-overlapping bootstrap CIs. This matches Regime α's
pre-specified criterion (both pairs agree across n=3 and
n=6).

Alternatives considered and rejected.

- Regime A (monotonic): rejected because the gap-only vs
  no-reference contrast's CI overlaps zero; the gradient is
  not monotonic across all three steps.
- Regime C (gap-suffices): rejected because full vs gap-only
  excludes zero on the positive side; the gap scalar does
  not suffice on its own.
- Regime D (irrelevant): rejected because two of three
  contrasts exclude zero with very large effects (Cliff's δ
  full vs no-reference = +0.605).
- For E5: Regimes β (one inverts), γ (both invert), and δ
  (ambiguous via overlapping CIs) all rejected — no
  inversions occurred and CIs do not overlap within either
  load-bearing pair.

Reference.

- `thesis/writing/chapter4_comparative_decomposition_design.md`
  §7.2.
- `thesis/writing/chapter4_extra_trajectories_design.md`
  §6.1.
- `thesis/artifacts/chapter4_decomposition_analysis.json` and
  `chapter4_decomposition_analysis.md` (verify script output).
- `thesis/artifacts/chapter4_extra_trajectories_n6_regime.json`
  and the four per-cell `*_n6.json` artifacts.
- Findings-log entries dated 2026-05-23 (the two regime
  findings).

---

**2026-05-22 — Examiner-response revision sprint adopted; stretch package locked.**

Decision. Two independent examiner reads (the second
consolidated, dated 2026-05-22, available in
`thesis/docs/08_revision_plan.md`) converged on a "major
revisions" verdict driven by claim-scope mismatch and the
absence of an external baseline. The thesis adopts the
*stretch package* on the empirical side: one no-reference
control cell (E1), one gap-only control cell (E2), and
extra validation trajectories on four key cells (E5), for
180 new LLM calls total. On the analytical side: classical
heuristic baselines for `h_eoh` (E4), leave-one-out
sensitivity (E6), catastrophe-threshold sweep (E7), and
§4.4 exploratory relabel (E8), all no-LLM-budget. On the
writing side: scope paragraphs everywhere, statistical
language sweep, reference verification, budget table, and
the new examiner's Fix 1–13 substitutions.

Reason. The single-cell E1-only option would satisfy the
C1 critique but would not isolate which comparative-content
component is load-bearing. Running E1 + E2 together
decomposes the comparative content (reference code vs gap
scalar) and gives substantially more interpretive power
than E1 alone. The E5 trajectory extension materially
addresses the n=3 critique on the cells whose findings
carry the most weight. The no-LLM analyses (E4, E6, E7,
E8) cost nothing in LLM budget and convert four examiner
attacks into reported analyses.

Alternatives considered and rejected.
- E1-only minimal package (60 LLM calls). Rejected on the
  decomposition-power argument above.
- E1 + E2 without E5 (120 LLM calls). Considered;
  rejected because the n=3 critique is severe enough on
  the four key cells that the marginal 60-call extension
  to n=6 is high-value.
- E1 + E2 + E3 (scalar-only / no-examples baseline; 180
  LLM calls). Rejected because E3 is redundant with E1 for
  the C1 critique; the extra 60 calls are better spent on
  E5.
- E1 + E2 + E5 + E9 (different reference replication;
  300+ LLM calls). Rejected on time budget; E9 is named
  as future work.
- Demote all empirical work to limitations prose only.
  Rejected because the C1 critique requires at least one
  external-baseline cell to satisfy.

Reference.
- `thesis/docs/08_revision_plan.md` (this commit).
- Consolidated examiner report (archived in user's records).
- Earlier examiner report (archived in user's records).

---

**2026-05-22 — Comparative-content decomposition scope locked: E1 (no-reference) + E2 (gap-only), both matched-paired to chapter 5's `stratified_representative` L1 cell.**

Decision. Two new experimental cells run together as a
three-condition decomposition with the chapter-5 cell as
the full-comparative anchor. E1 strips both reference code
and gap scalar; E2 strips only reference code, retaining
gap scalar. Both run at `stratified_representative @ L1 @
k=4`, 60 sanitization-ok proposals each, matched-paired
by `set_index` to the chapter-5 60 stratified_representative
L1 sets. Seed namespaces: `ch4noref:` for E1, `ch4gaponly:`
for E2.

Reason. The matched-pair three-condition design lets the
joint reading decompose the comparative content into its
two component fields (reference code, gap scalar) and
identify which is load-bearing. The four pre-specified
outcome regimes (A monotonic, B code-matters, C gap-
suffices, D irrelevant) each have a pre-written prose
response in W-§4.5.

Alternatives considered and rejected.
- E1 only (no-reference, strip both). Rejected on the
  decomposition-power argument: cannot isolate which
  comparative component matters.
- Independent draws rather than matched sets. Rejected on
  statistical-power grounds; matched-pair design is
  substantially more powerful at n=60.
- Run E1 first, then decide on E2 based on E1's result.
  Rejected because running together maintains constant
  experimental conditions (model version, time window,
  pool) and makes the matched-pair design's defense clean.
- Including L2 in the decomposition. Rejected to avoid
  entangling the trace rendering rule limitation (D5).

Reference.
- `thesis/writing/chapter4_comparative_decomposition_design.md` §1–§7.
- `thesis/docs/08_revision_plan.md` §1.1, §3 (Phase B).

---

**2026-05-22 — E1 task-instruction wording locked verbatim.**

Decision. The E1 (no-reference) task-instruction wording is
character-identical across all 60 calls:

> You are given a heuristic scoring function `incumbent`
> and four instances of online bin packing on which the
> incumbent's behavior is shown by `incumbent_bins_used`.
> Propose a revised scoring function whose behavior
> improves performance — that is, uses fewer bins — on
> these instances and on the broader instance distribution
> they represent. Return only the revised function.

Reason. Locked verbatim because the manipulation's
defensibility depends on the precise substitution being the
only thing different about the prompt's non-counterexample
content. The locked wording does not mention "reference",
"alternative", "comparison", or "gap".

Reference.
- `thesis/writing/chapter4_comparative_decomposition_design.md` §5.2.

---

**2026-05-22 — E2 task-instruction wording locked verbatim.**

Decision. The E2 (gap-only) task-instruction wording is
character-identical across all 60 calls:

> You are given a heuristic scoring function `incumbent`
> and four instances of online bin packing on which the
> incumbent's behavior is shown by `incumbent_bins_used`.
> For each instance, a `gap_bins` field reports the signed
> difference between the incumbent's bin count and the bin
> count achieved by a fixed reference scoring function not
> shown here (positive `gap_bins` means the incumbent uses
> more bins than the reference; negative means fewer).
> Propose a revised scoring function whose behavior
> improves performance — that is, reduces the bin count —
> on these instances and on the broader instance
> distribution they represent. Return only the revised
> function.

Reason. The "not shown here" phrasing is deliberate; it
tells the LLM the gap is real but the implementation is
withheld, which is the precise manipulation E2 tests.

Reference.
- `thesis/writing/chapter4_comparative_decomposition_design.md` §5.3.

---

**2026-05-22 — Comparative-content prompt-rendering schema locked for E1 and E2.**

Decision. E1 and E2 use separate prompt builders
(`thesis/code/chapter4_noref/prompt_builder.py` and
`thesis/code/chapter4_gaponly/prompt_builder.py`); the
chapter-5 builder is preserved unchanged. E1's
counterexample-block schema includes `instance_id`,
`item_distribution`, `item_samples`, `incumbent_bins_used`,
and nothing else; E2's schema additionally includes
`gap_bins` and (option (a) default) `reference_bins_used`.
No `reference_heuristic:` top-level block in either cell's
rendered prompt. Unit tests assert: E1 has no `reference`
or `gap` substring; E2 has `gap_bins` field present and no
reference source code anywhere.

Reason. Separate builders prevent accidental regression of
the chapter-5 rendering and make the manipulation auditable
in code.

Reference.
- `thesis/writing/chapter4_comparative_decomposition_design.md` §4.

---

**2026-05-22 — Pre-specified outcome regimes A–D locked for E1 + E2.**

Decision. Four mutually exclusive outcome regimes
pre-specified on the joint matched-pair Δ_step CI analysis:

- **Regime A (monotonic):** full > gap-only > no-reference.
- **Regime B (code-matters):** full > gap-only ≈ no-reference.
- **Regime C (gap-suffices):** full ≈ gap-only > no-reference.
- **Regime D (irrelevant):** full ≈ gap-only ≈ no-reference.

The W-§4.5 prose response is pre-written for each regime;
the regime that obtains determines which prose template is
used. Mixed / non-monotonic results are named honestly as a
finding the thesis does not have power to interpret
further (future work in §5.5).

Reason. Outcome-regime pre-specification prevents post-hoc
rationalization. The cells' defensibility under examiner
questioning rests partly on the prose responding
consistently to whichever regime the data lands in, with
the response rule documented before the result is known.

Reference.
- `thesis/writing/chapter4_comparative_decomposition_design.md` §7.

---

**2026-05-22 — `ch4noref:` and `ch4gaponly:` seed namespaces introduced.**

Decision. Per-call seeds derive from `ch4noref:` and
`ch4gaponly:` respectively. CounterexampleSet draws reuse
the chapter-5 sets unchanged (matched-pair design); only
the per-call LLM seed is namespace-fresh.

Reason. Reusing chapter-5 seeds wholesale would risk
identical proposals if (prompt content, sampling seed)
coincided. Fresh namespaces isolate the new cells' per-call
randomness while preserving the matched-pair design at the
CounterexampleSet level.

Reference.
- `thesis/writing/chapter4_comparative_decomposition_design.md` §6.2.

---

**2026-05-22 — E4 (classical heuristic baselines for h_eoh) scope locked.**

Decision. Four classical bin-packing heuristics (First Fit,
Best Fit, Worst Fit, First Fit Decreasing) computed
deterministically on all five splits (train_select,
train_step, train_gate, dev, test_ood). FFD labeled
*offline* in §3.3 prose and in any table caption.
Tie-breaking: Best Fit and Worst Fit break ties by bin
creation order (earliest first). Metrics per (baseline,
split): mean / std / median / min / max `bins_used`, plus
mean delta vs h_eoh and per-instance win/loss/tie counts.
Single artifact: `thesis/artifacts/chapter3_incumbent_baselines.json`.

Reason. The §3.3 prose currently asserts that `h_eoh` is
"strong" without any external reference. Comparing against
classical online heuristics turns the characterization into
a concrete relative-strength claim; this directly addresses
examiner D9's incumbent-characterization question at zero
LLM budget.

Reference.
- `thesis/writing/chapter3_incumbent_baselines_design.md`.

---

**2026-05-22 — E5 (extra validation trajectories) scope locked: 4 cells × 3 trajectories × 5 steps = 60 LLM calls.**

Decision. Four cells extended from n=3 to n=6 validation
trajectories:

1. `stratified_representative @ L1 @ k=4` (chapter 5).
2. `worst_plus_best @ L1 @ k=4` (chapter 5).
3. `stratified_representative @ L2 @ k=1` (chapter 7).
4. `worst_only_at_k1 @ L2 @ k=1` (chapter 7).

Extension uses existing trajectory drivers with fresh
`set_index` values 3, 4, 5 under the `ch4extra:` namespace.
Pre-specified outcome regimes α (agree), β (one inverts),
γ (both invert), δ (ambiguous).

Reason. The cells named carry the load-bearing claims in
chapter 5's validation discussion (regime-dependent
ranking) and chapter 7's primary cardinality contribution
(L2 k=1 gap). Material n=3 → n=6 extension on these four
cells is the smallest sample-size intervention that
materially defends against the n=3 critique.

Alternatives considered and rejected.
- Extend all validation cells to n=6 (costs ~200 LLM
  calls). Rejected on budget; the four key cells are
  sufficient.
- Extend to n=10 on the two highest-priority cells.
  Rejected: n=6 is the inflection point where defense
  return per LLM call drops.

Reference.
- `thesis/writing/chapter4_extra_trajectories_design.md`.

---

**2026-05-22 — §4.5.4 robustness analyses (E6 + E7 + E8) scope locked.**

Decision. Three analyses on existing data, no LLM budget,
consolidated into §4.5.4:

- **E6 leave-one-out / median sensitivity** on all
  validation cells in Tables 4.4 and 4.10.
- **E7 catastrophe-threshold sweep** at −10, −20, −50,
  −100, −200 on chapter-6 and chapter-5 primary-batch
  cells.
- **E8 §4.4 exploratory relabel** (load-bearing, single
  sentence). Optional Benjamini-Hochberg FDR correction at
  α=0.05 on the §4.4 family of cell-pair comparisons.

Reason. Three examiner attacks (D7 outlier, D4 threshold
justification, D2 multiple-comparison) addressed at zero
LLM budget by reporting analyses on existing data.

Reference.
- `thesis/writing/chapter4_robustness_analyses_design.md`.

---

**2026-05-22 — §4.5 structural placement locked: additive new section, not weave-in.**

Decision. New empirical and analytical results from E1,
E2, E7, E8 land in a new §4.5 "Additional controls and
robustness checks" subsection in the compiled thesis,
rather than being woven into §4.2 / §4.3 / §4.4. E4 results
land in §3.3 (incumbent characterization). E5 + E6 results
extend Tables 4.4 / 4.10 in place. A methodological note
in §3.4 or §4.5 names the table extensions.

Reason. Three justifications:

1. **Minimizes revision risk.** Existing §4.2 / §4.3 /
   §4.4 prose stays intact except for soft language fixes
   (W-LANG). The new results are reported in a self-
   contained section that names itself as an addition.
2. **Reads honestly to an examiner.** A section titled
   "Additional controls and robustness checks" signals
   scope-honest extension, not late reinterpretation of
   original findings.
3. **Matches the post-hoc nature of the experiment.** E1
   and E2 are run after the original chapter-5 experiments;
   reporting them in §4.5 preserves the chronological
   reading and makes the matched-pair design's defense
   clean.

Alternatives considered and rejected.
- Weave new cells into existing §4.2 (selection axis)
  subsections. Rejected on revision-risk grounds: would
  require rewriting §4.2 substantially and risks
  destabilizing finishes that already pass internal
  review.
- Standalone Chapter 5 reorganization. Rejected as
  excessive scope for the time budget.

Reference.
- `thesis/writing/chapter4_comparative_decomposition_design.md` §1.3.
- `thesis/docs/08_revision_plan.md` §1.4.

---

**2026-05-18 — Stage 15: fix four chapter-internal §X.Y references introduced by earlier-stage edits.**

Decision. A post-Stage-14 sweep of all `§X.Y` references in
the docx found four chapter-internal references that my
Stage-12 edits introduced using chapter6.md / chapter7.md
locked-source numbering (§6.X, §7.X) rather than the
integrated-manuscript numbering (§4.3.X, §4.4.X). In the
integrated manuscript, chapter6.md is §4.3 and chapter7.md
is §4.4, so the four references would have read as
broken cross-references to non-existent Chapter 6 / Chapter 7
sections (Chapter 6 is Conclusion in the integrated
manuscript, not Structure; there is no Chapter 7).

Four fixes applied via `.stage15_merge.py`:

- "`tabulation in §6.3.2`" → "`tabulation in §4.3.3.2`"
  (threshold-switch footnote in the §4.3 forensic prose).
- "`Chapter 6 §6.5 reports`" → "`§4.3.5 reports`"
  (falsification clause in the §4.2 → §4.3 bridge).
- "`§6.5.1 reads`" → "`§4.3.5.1 reads`" (continuation of
  the falsification clause).
- "`by the §7.2 boundary`" → "`by the §4.4.2 boundary`"
  (boundary clarification in §4.4.3.3).

Audit. `stage15_audit.py` reports the same green slate as
Stage 14: 0 Sense-A hits across the 22 forbidden terms;
Figure 4.1..4.11 all present; Table 4.1..4.18 all present;
document.xml well-formed; 20 images / rels; zip core entries
intact. document.xml size changed by -2 chars (the new
numbers are slightly shorter than the originals). Output:
`thesis/writing/Thesis Chaps.stage15_merge.docx`.

Reason. The locked .md sources keep chapter6.md's §6.X and
chapter7.md's §7.X numbering as provenance — they are
chapter-internal references inside each file's own
namespace. The integrated docx must translate those into
§4.3.X / §4.4.X for cross-references to resolve. Earlier
edits propagated my source-file phrasings into the docx
without the namespace translation; Stage 15 closes the
gap. The .md sources themselves are left as-is (their §6.X
and §7.X are correct within their own file).

Alternatives considered. (1) Renumber the locked .md
sources too. Rejected because each .md is its own
self-contained document with its own internal numbering;
renumbering would obscure the historical provenance the
locked-source discipline exists to preserve. (2) Leave the
docx with the §6.X / §7.X refs and add an editor note.
Rejected because a thesis examiner would parse them as
broken cross-references on first read.

Artifacts. `.stage15_merge.py` (the fix script);
`.stage15_audit.py` (audit run);
`thesis/writing/Thesis Chaps.stage15_merge.docx` (the new
defense-ready candidate).

---

**2026-05-18 — Stage 14: §4.2 figures + Stage-10 cosmetic cleanups.**

Decision. Stage 13 completed the empirical-fix program but
left two presentation-level issues from the original
ch4_experimental_critique_2026-05-18.md still open: (1)
§4.2 had zero figures in the manuscript while §4.3 and §4.4
each had several; (2) the Stage-10 closing-audit open list
flagged five bare design-doc shortcut references
(`§12`, `§18.6`, `§18.8`, `§18.9 ×2`) and a Conclusion
`§3 → "Chapter 3"` cosmetic. Of the five shortcuts, two
(`§12`, `§18.6`) had already been prefixed in the locked
sources; three (§18.8, §18.9 ×2) and the §3 cosmetic remained.

Stage 14 addresses both. The §4.2 figures were generated
deterministically from the committed records:

- **Figure 4.1** (new) — per-strategy Δ_step distribution
  across the five selection strategies (n = 60 sanitize-ok
  proposals per strategy) as a violin plot with overlaid IQR
  boxes. Source: `chapter5_primary_batch_gemini/*.json`.
- **Figure 4.2** (new) — validation-batch cumulative Δ_step
  trajectories across the three validation strategies
  (3 trajectories × 5 steps per strategy). Source:
  `chapter5_validation_batch_gemini/*_trajectory_summary.json`.

Both figures generated by the new committed script
`thesis/code/experiments/chapter5_make_figures.py` (matplotlib
3.10, headless, no LLM calls). PNGs at
`thesis/notes/stage14_figure_preview/`.

Renumbering. Inserting two new figures at the front of the
§4 sequence required shifting every existing Figure 4.X
reference: `Figure 4.1..4.9` → `Figure 4.3..4.11`, processed
high-to-low with a digit-boundary regex to avoid 4.1↔4.11
substring collisions. 20 cross-references updated in the
docx; 0 in chapter5.md (no Figure 4.X refs there); the
chapter6.md and chapter7.md locked sources were renumbered
to match (deltas = 0 chars; same digit counts).

Bare-shortcut tightening (manuscript-level only; locked
sources retain the cited form for provenance):

- "`The §18.8 full-dev pass`" → "`The design-doc §18.8 full-dev pass`"
- §4.3 anchor-reproduction prose: "`The §18.9 anchor-reproduction analysis`" → "`The design-doc §18.9 anchor-reproduction analysis`" (primary occurrence)
- §4.4 trajectory-anchor-reproduction prose: "`The §18.9 anchor-reproduction analysis applied to the validation`" → "`The design-doc §18.9 anchor-reproduction analysis applied to the validation`" (validation occurrence)

Conclusion cosmetic: "`findings under §3's methodology`"
→ "`findings under Chapter 3's methodology`".

Audit. `stage14_audit.py` reports: 0 Sense-A hits across the
22 forbidden terms; `Figure 4.1..4.11` all present;
`Table 4.1..4.18` all present; document.xml well-formed;
all zip core entries present; 20 image files in
`word/media/` (was 18; +2 for image19.png / image20.png);
20 image-relationships in rels (was 18; +2 for rId25 /
rId26). Word count: ~45.4k. docx size moves from 1.99 MB
(Stage 13) to 2.20 MB (Stage 14), with the +0.21 MB driven
by the two embedded PNGs.

Reason. The original audit flagged §4.2's empty figure slot
as a presentational gap; closing it removes the most visible
visual asymmetry between §4.2 and the rest of Chapter 4. The
Stage-10 open-item cleanups are now closed at the docx level,
so the submission artifact has none of the bare design-doc
shortcuts the closing audit flagged.

Alternatives considered. (1) Skip the figure insertion and
ship without §4.2 figures. Rejected because an examiner
reading §4.2 against §4.3 / §4.4 will immediately notice
the asymmetry; defending it as "no figures were needed"
would have read worse than the simple readability fix
generating two figures provides. (2) Number the new
figures as Figure 4.10 / 4.11 to avoid renumbering. Rejected
because §4.2 precedes §4.3 / §4.4 in the manuscript and
out-of-physical-order figure numbers in a thesis would
puzzle a reader. (3) Number them as Figure 4.2.a / 4.2.b
(sub-numbered to §4.2). Rejected because the rest of the
chapter uses flat Figure 4.X numbering and mixing schemes
would be inconsistent.

Artifacts. `.stage14_merge.py` (integration script);
`.stage14_audit.py` (audit script);
`thesis/code/experiments/chapter5_make_figures.py` (figure
generator; deterministic);
`thesis/notes/stage14_figure_preview/figure_A_strategy_violin.png`
and `figure_B_trajectory_traces.png` (rendered figures,
also embedded as `word/media/image19.png` and
`image20.png`); `thesis/writing/Thesis Chaps.stage14_merge.docx`
(the new defense-ready candidate).

---

**2026-05-18 — Stage 13: propagate the four deferred whole-paragraph / table additions into the docx.**

Decision. Stage 12 left four content additions in the locked
`.md` sources without propagating them into the docx because
each required constructing a fresh `<w:p>` or `<w:tbl>` block
at a specific docx insertion point rather than a simple
string replacement. Stage 13 propagates all four through the
existing `unpack.py` / `pack.py` toolchain. The Stage-12 docx
is retained as a rollback point;
`Thesis Chaps.stage13_merge.docx` is the new defense-ready
candidate.

What was added to the docx:

- **§4.2 / §4.2.4 — n = 60 sufficiency defense paragraph.**
  Inserted immediately after the Cliff's δ "small effect"
  threshold prose. States that the smallest pairwise δ
  crossing |0.147| sits well above the sampling noise floor
  at this sample size, and that no dedicated power calculation
  is run because the headline finding is the absence of
  stochastic dominance.

- **§4.2 / §4.2.5 — "Small validation sample" limitation
  paragraph.** Inserted in §4.2.5's limitations list after
  the "Single structural level" limitation. Acknowledges
  n = 3 trajectories per strategy, the +14.20 outlier driving
  stratified's mean above its median, and the sign-stability
  of the headline rank-inversion across the three trajectories
  per cell.

- **§4.2 / §4.2.6 — Falsification clause for the Chapter-6
  prediction.** Inserted in the §5.5.3 forward-pointer to
  Chapter 6 prose. States the rate band that would falsify
  the prediction and the chapter-6 sections that report the
  actual outcome.

- **§4.3 / §4.3.2 — Table 4a (jackknife sensitivity).**
  Inserted after the "directionally consistent but not on
  their own a defense" passage. Six-row Word `<w:tbl>` with
  bold-header preamble paragraph, the table itself
  (7 columns × 7 rows including header), and a readback
  paragraph that names the result: CI lower bound stays
  positive at every drop level from 0 to 5 catastrophic
  records per cell; the interaction's amplitude depends on
  the worst records, but its sign does not. The table was
  generated from
  `thesis/artifacts/chapter6_jackknife_sensitivity.json`
  by `.stage13_merge.py`.

Audit. `stage13_audit.py` re-ran the Stage-10 closing-audit
checks against the Stage-13 docx and reports: 0 Sense-A hits;
all Figure 4.1..4.9 and Table 4.1..4.18 references intact;
13 Heading1, 44 Heading2, 71 Heading3, 30 Heading4 (matches
Stage 12); 18 images and rels (matches Stage 12); 23 tables
(was 22 — the new jackknife table); document.xml well-formed;
all expected zip core entries present.

Stage 13 file deltas. Word count rises from Stage 12's
45,258 to Stage 13's word count after the four insertions;
document.xml grows by 44,933 chars; total docx size moves
from 1,993,700 bytes (Stage 12) to 1,996,176 bytes
(Stage 13).

Reason. Closing the gap between the locked-source state and
the docx state so the dissertation submission artifact (the
docx) is fully consistent with the source-of-truth `.md`
files. Each of the four additions is defense-relevant on its
own: the n = 60 paragraph pre-empts the most common
sample-size challenge against Cliff's δ findings; the
n = 3 paragraph names the smallest sample any headline
number in the chapter rides on; the falsification clause
satisfies the standard "what would falsify your prediction"
question for the Chapter-6 forward-pointer; and the
jackknife table directly refutes the audit's strongest
defense-vulnerability point — that the §4.3 cross-strategy
interaction is driven by 2-4 catastrophic records.

Alternatives considered. (1) Leave the four additions only
in the locked `.md` sources. Rejected because the docx is
the submission artifact and the audit's defense-vulnerability
points require the additions to be visible to a reader of
the docx, not buried in a source file the examiner is
unlikely to open. (2) Re-integrate chapter5.md / chapter6.md
into the docx wholesale. Rejected because Stage 11's title,
abstracts, figures, references, and Stage 12's text edits
would be re-applied, increasing risk relative to surgical
inserts.

Artifacts. `.stage13_merge.py` (the integration script);
`.stage13_audit.py` (audit script);
`thesis/writing/Thesis Chaps.stage13_merge.docx` (the new
defense-ready candidate).

---

**2026-05-18 — Stage 12: defense-readiness fixes to §4.2 / §4.3 / §4.4 after pre-submission cross-check against the artifact JSONs.**

Decision. After the Stage-11 merge, a section-by-section
audit of the empirical chapter against the canonical artifact
JSONs (`thesis/artifacts/chapter{5,6,7}*.json`,
`thesis/docs/06_findings_log.md`,
`thesis/docs/04_experimental_matrix.md`) identified 22 issues
(7 high, 9 medium, 6 low) across the three sections. The
critique is preserved at
`thesis/notes/ch4_experimental_critique_2026-05-18.md`. Of the
22 issues, 18 were addressed in Stage 12; the remaining 4 are
manuscript-level cosmetic items already on the Stage-10 open
list (§4.2 numbering reset, §4.2 figures slot review, design-
doc-shortcut prefix tightening, optional Word TOC insertion).

What was changed in the locked source files:

- `thesis/writing/chapter5.md` (§4.2): exact bracket
  [−12.93, −2.53] replaces "approximately [−13, −3]"; IQR
  equality "(both 7.42, identical to two decimals)" replaces
  "both roughly 7.4"; "Between 20.0% and 26.7% (mean 23.3%,
  n = 60 per strategy)" replaces "Approximately one proposal
  in four"; Cliff's δ thresholds now cite Romano et al.
  (2006); a one-paragraph n = 60 sufficiency defense was
  added at the end of §5.2.4; the "behaviorally distinct
  proposals tend to land" claim was tightened to "in this
  45-step sample" with a 95% binomial upper bound; a new
  "Small validation sample" limitation paragraph was added
  to §5.5.2 covering the n = 3 trajectory sample size; the
  §5.5.3 forward prediction now carries an explicit
  falsification clause.

- `thesis/writing/chapter6.md` (§4.3): a new Table 4a
  (jackknife sensitivity) was added immediately after the
  primary statistical-defense passage in §6.3.2, showing that
  the cross-strategy interaction CI excludes zero out to
  drop = 5 catastrophic records per cell (lower bound stays
  positive across all 6 jackknife rows tested); the §6.3.5
  prose was annotated to flag the Δ_step < −100 / Δ_step
  < −50 threshold switch between Analysis B and §6.3.2; the
  §6.4.4 cross-batch reproducibility passage now carries a
  §5.2.2 forward-pointer for the methodological reading; the
  §6.3.5 Analyses P–S citation now resolves to the surfaced
  `chapter6_shown_vs_unshown_analyses_PQRS.json` artifact;
  the §6.7.1 rendering-rule distortion paragraph now traces
  the N = 60 distortion numbers to `chapter6_design.md` §9.2
  and the pool baseline to
  `chapter6_trace_stats.json::pool_aggregates`; the Table 5
  caption was rewritten to disambiguate the diff-hash subset
  sample sizes from the full class counts.

- `thesis/writing/chapter7.md` (§4.4): a new paragraph in
  §7.3 discloses the CH7-12 and CH7-13 retry-wobble
  (CH7-12 went −44.4 at n = 28 to −93.1 at n = 60; CH7-13
  went −208.1 at n = 22 to −155.1 at n = 60), citing the
  findings log; §7.3.3's "stratified beats worst_plus_best at
  L2 at every k" was corrected to explicitly name
  `worst_only_at_k1` as the k = 1 comparator per the §7.2
  boundary substitution; §7.3.2's monotonicity discussion now
  names the structural reason for the null verdict — the
  Spearman test runs on the 3-or-4 cell-means as data points
  (not the underlying 180–240 proposals), so the test is
  irreducibly low-power within the locked N = 60 rendering
  rule's L2 cardinality range.

- `thesis/writing/references.md`: Romano et al. (2006)
  added to support the Cliff's δ threshold citation.

What was generated as new artifacts:

- `thesis/artifacts/chapter6_primary_batch_overview.json`
  (7,397 bytes). The §6.2-cited full-batch overview that
  was missing from the committed artifacts. Per-cell mean,
  median, std, IQR, percentiles, catastrophic and positive
  tail masses for all 4 chapter-6 cells over the n = 240
  primary batch. Generated deterministically from the
  per-record JSONs in
  `thesis/results/chapter6_primary_batch_gemini/`.

- `thesis/artifacts/chapter6_jackknife_sensitivity.json`
  (2,774 bytes). Six-row jackknife sensitivity table for
  the §6.3.2 cross-strategy mean-Δ_step CI. Bootstrap with
  n_resamples = 10 000 percentile, seed = 601. The CI
  excludes zero at every drop level tested (drop = 0 through
  drop = 5 catastrophic records per cell); lower bound moves
  from +9.63 (drop = 0) to +8.16 (drop = 5) and stays
  positive throughout. This is the strongest available
  defense against the "interaction is just outliers" reading.

- `thesis/artifacts/chapter6_shown_vs_unshown_analyses_PQRS.json`
  (12,801 bytes). Surfaces Analyses P (per-cell
  distributions), Q (matched-pair), R (catastrophe rates),
  S (bootstrap CIs) from
  `thesis/results/chapter6_primary_batch_gemini/_shown_vs_unshown_analysis.json`
  as a committed artifact for §6.3.5 to cite. The
  cross-strategy interaction CIs on shown
  (+76.50 [+8.37, +156.31]) and unshown
  (+76.14 [+7.04, +151.67]) variants both exclude zero.

- `thesis/code/experiments/chapter6_make_overview_and_jackknife.py`
  (8.2 KB). Deterministic generator for the two new
  Chapter 6 artifacts; no LLM calls; reproducible from the
  committed per-record JSONs.

What was changed in the manuscript docx:

- `.stage12_merge.py` propagated 13 of the chapter source-
  text edits into the manuscript docx as XML-level
  string-replacements through the existing
  `scripts/office/unpack.py` / `pack.py` toolchain. All 13
  edits applied directly; no tolerant cross-run matching
  was needed. Output:
  `thesis/writing/Thesis Chaps.stage12_merge.docx`. Word
  count: 45,258 (Stage 11: 44,797; Stage 10: 41,545). The
  Stage-11 docx is retained as a rollback point.

Audit. `stage12_audit.py` re-ran the Stage-10 closing-audit
checks against the Stage-12 docx and reports: 0 Sense-A hits
across the 22 forbidden terms; all Figure 4.1..4.9 and
Table 4.1..4.18 references intact; 13 Heading1, 44 Heading2,
71 Heading3, 30 Heading4 (matches Stage 11); 18 images and
rels (matches Stage 11); document.xml well-formed; all
expected zip core entries present.

What was not propagated to the docx (deferred to a future
docx pass or accepted as locked-source-only):

- The four whole-paragraph additions to chapter5.md (n = 60
  sufficiency paragraph, n = 3 trajectory limitation, §5.5.3
  falsification clause expansion) and the
  Table 4a jackknife block in chapter6.md exist in the
  locked .md sources but were not propagated as new
  paragraphs into the docx in Stage 12 because each requires
  constructing a properly-formatted `<w:p>` (and, for the
  table, `<w:tbl>`) block at a specific docx insertion
  point. The numerical content backing each is in the
  surfaced artifacts; the locked-source .md files are
  authoritative for the textual additions.

Reason. The pre-submission audit identified two
defense-vulnerability points that an examiner could
discover from the git/log history: the §4.3 cross-strategy
CI's catastrophe-tail dependence, and the §4.4 retry-wobble
on CH7-12 and CH7-13. Both were defended directly: the
jackknife table proves the CI lower bound stays positive
without the catastrophic records, and the retry-wobble is
now disclosed in §4.3's text rather than only in the
findings log. The remaining fixes (terminology precision,
artifact-citation resolution, missing baseline citation,
sample-size structural explanation) close audit-trail gaps
the artifacts already documented.

Alternatives considered. (1) Do nothing — accept the
22 issues and rely on Stage-10's "defense-ready at scope"
verdict. Rejected because two of the issues (retry-wobble,
catastrophe-tail dependence) are git-discoverable and would
be the first questions an adversarial examiner asks.
(2) Make changes only in the locked sources and skip the
docx propagation. Rejected because the dissertation
submission is the docx; the locked sources serve as
provenance, not as the submission artifact.
(3) Re-integrate the locked sources into the docx from
scratch. Rejected because Stage 11's title/abstracts/figures/
references work would have to be redone.

Artifacts. `.stage12_merge.py` (Stage-12 integration
script); `stage12_audit.py` (the audit run);
`thesis/notes/ch4_experimental_critique_2026-05-18.md`
(the read-only critique that scoped Stage 12);
`thesis/artifacts/chapter6_primary_batch_overview.json`,
`thesis/artifacts/chapter6_jackknife_sensitivity.json`,
`thesis/artifacts/chapter6_shown_vs_unshown_analyses_PQRS.json`
(new committed artifacts);
`thesis/code/experiments/chapter6_make_overview_and_jackknife.py`
(reproducer for the first two);
`thesis/writing/Thesis Chaps.stage12_merge.docx` (the new
candidate manuscript); `thesis/writing/chapter5.md`,
`thesis/writing/chapter6.md`, `thesis/writing/chapter7.md`
(locked sources updated in-place with all 18 fixes);
`thesis/writing/references.md` (Romano 2006 added).

---

**2026-05-18 — Stage 11: selective merge of the 2026-05-18 user-edited draft into the Stage-10 baseline.**

Decision. A user-edited draft was dropped into
`thesis/writing/Thesis Chaps (last edited version ).docx` on
2026-05-18, dated three days after Stage 10 closed. It was not
produced through the Stage-7d–10 program and did not pass through
`scripts/office/unpack.py` / `pack.py`. A read-only audit
(`thesis/notes/new_draft_audit_2026-05-18.md`) characterized the
draft as **partially valid** — it contained substantive
additions worth keeping (Abstract, Arabic abstract, expanded
Introduction with proper citations, LLM-AHD system full-name
expansions, 5 new figures, 2 new reference tables, References
section) **and** regressions that broke Stage-10 invariants
(3 Sense-A `large-headroom` hits, Chapter-4 figure/table
renumbering reverted to bare `Table 1..12` / `Figure 1..N`,
heading demotions in §4.4, Chapter-5 paragraph collapses,
fabricated `§9.4` and `design-doc §11.7` cross-references, an
imprecise `§3.5 → "Chapter 4"` substitution, and a global
curly-quote sweep).

The chosen response was a **surgical merge** rather than a
wholesale replacement: keep `Thesis Chaps.docx` (Stage 10) as
the source of truth, write a new
`Thesis Chaps.stage11_merge.docx`, and port only the additive
wins into it. The merge was implemented by `.stage11_merge.py`
using the same `unpack.py` / `pack.py` toolchain Stages 7d–10
used. The script extracts named XML chunks from the
user-edited draft by plain-text anchor matching, remaps rIds
rId20..rId24 for the five new image files, validates each
chunk against the 22-term Sense-A blocklist before insertion,
and writes the result back as a sibling file. Stage 10's
`Thesis Chaps.docx` was not modified.

What was ported (additive only; the only Stage-10 deletion was
the two title-page paragraphs replaced by the new title block):

- Title-page rework + TOC placeholder.
- English Abstract (Heading1 + paragraph + keywords).
- Arabic abstract ملخّص (Heading1 + paragraph + keywords).
- Introduction first paragraph expanded with VRP / Job-Shop /
  Bin-Packing examples and Toth & Vigo (2014), Pinedo (2016),
  Burke et al. (2013) citations.
- New "Problem statement" Heading2 in the Introduction.
- Ten LLM-AHD system full-name expansions in Ch1 §1.6 (AEL,
  EoH, HSEvo, MEoH, EoH-S, ReEvo, TPD-AHD, LaGO, BehaveSim,
  PathWise) as paragraph-level XML replaces that preserve the
  user-edited draft's bold-name run formatting.
- Figure 1.2 (four-level AHD genealogy graphic) in Ch1 §1.6
  after the Table 1.1 row prose.
- Figure 2.2 (three views of informativeness) in Ch2 before
  §2.5.
- Figure 2.3 (worked example on instance i9) in Ch2 §2.5.
- Figure 2.4 (three-axis design space) in Ch2 §2.8.
- Figure 3.2 (end-to-end refinement workflow) in Ch3 §3.5.
  Image files copied as `image14.png` through `image18.png`;
  rIds rId20..rId24 added to `word/_rels/document.xml.rels`.
- Table 3.1 (score / fitness / EoH-native objective / gap
  definitions and roles) in Ch3 §3.2.
- Table 3.2 (five-subset split design at a glance) in Ch3 §3.4.
- References section appended at end. Body is the union of
  `thesis/writing/references.md` (48 entries) with the
  user-edited draft's References block (50 entries); the 47
  in-both entries agreed byte-for-byte (modulo italics
  formatting and one curly-vs-straight apostrophe), and the
  two only-in-new-draft entries (Pinedo 2016 and Toth & Vigo
  2014) are exactly the Introduction's new citations.
  `references.md` was updated alongside this entry to add
  both, bringing both sources to 50 entries.

What was rejected (Stage-10 invariants preserved):

- Sense-A `large-headroom regime` reintroductions in §4.2 and
  §4.4 of the user-edited draft.
- Chapter-4 figure renumbering reversion (the locked
  `Figure 4.1..4.9` numbering was kept; the draft's bare
  `Figure 1..N` rewrite was discarded).
- Chapter-4 table renumbering reversion (the locked
  `Table 4.1..4.18` numbering was kept).
- §4.4 heading-level demotions (the user-edited draft
  demoted ~10 Heading3 nodes to Heading4; Stage 10's
  hierarchy was preserved).
- Chapter-5 paragraph collapses (the Stages 8a/b/c granular
  structure was preserved).
- The `§3.5 → "Chapter 4"` precision loss in the validation
  protocol description.
- The fabricated `(Section 4.2 §9.4, design-doc §11.7)`
  cross-reference in Ch4 §4.3.4.
- The global curly-quote sweep (cosmetic only; Word reapplies
  on save).
- The mixed `"chapter" → "section"` rewrites in Ch4 prose.

Audit. `stage11_audit.py` re-runs the Stage-10 closing-audit
checks against the merged docx and reports: 0 Sense-A hits
across the 22 forbidden terms; all Figure 4.1..4.9 and
Table 4.1..4.18 references intact; 18 images present (13
originals + 5 new); 13 Heading1 paragraphs (Stage 10 had 10;
+3 for Abstract, ملخّص, References); 156 Heading-styled
paragraphs total (Stage 10 had 153; +3 net); document.xml
well-formed; all expected zip core entries present; +3,252
words and +433 KB on disk (Stage 10: 41,545 words / 1.56 MB;
merged: 44,797 words / 1.99 MB). The 16 named wins verified
present in paragraph-level run-joined text.

Reason. The user-edited draft contained roughly 30% of new
content that genuinely improves manuscript readability and
defense readiness — citations the Introduction had been
missing, formal abstracts in both English and Arabic that a
thesis submission needs, full-name expansions that make Ch1
§1.6 readable to a non-AHD-specialist examiner, and substrate
figures for the conceptual chapter that pure prose was
carrying. Discarding the entire draft would have lost all of
that. Adopting it wholesale would have undone the Stage-10
closing-audit verdict (Sense-A retirement, Chapter-4
consolidated numbering, locked heading hierarchy) without a
decisions-log entry. The surgical merge keeps both
properties.

Alternatives considered. (1) Discard the user-edited draft
entirely and continue from Stage 10 unchanged. Rejected
because the citations, abstracts, and figure-based scaffolding
are real defense improvements. (2) Adopt the user-edited draft
wholesale and re-run a Stage-10-style cleanup pass on top to
back out the regressions. Rejected because backing out the
Chapter-4 renumbering would require rewriting every Chapter-5
cross-reference, and the regression count was larger than the
additive-merge count. (3) Build a merged docx and overwrite
`Thesis Chaps.docx` in place. Rejected in favor of writing
`Thesis Chaps.stage11_merge.docx` for user review before any
overwrite — matches the
`Thesis Chaps.pre_stage{7d,7e,8a,8b,8c,9,10}.docx` backup
discipline of prior stages.

Artifacts. `.stage11_merge.py` (the integration script);
`stage11_audit.py` (the audit script);
`thesis/notes/new_draft_audit_2026-05-18.md` (the read-only
characterization of the input draft);
`thesis/notes/stage11_figure_preview/` (the 5 candidate figures
staged for review prior to merge);
`thesis/writing/Thesis Chaps.stage11_merge.docx` (the merged
output, defense-ready candidate);
`thesis/writing/references.md` amended to add Pinedo (2016)
and Toth & Vigo (2014).

---

**2026-05-15 — Manuscript-writing program (Stages 7b–10): Chapter 4 consolidation, Chapter 5 drafting, Chapter 6 Conclusion, manuscript defense-readiness.**

Decision. The thesis manuscript was completed across a structured
ten-stage program. At the program's start (post-Stage-6 state),
the manuscript consisted of Introduction + Chapter 1 (Background)
+ Chapter 2 (Conceptual Framework) + Chapter 3 (Methodology), and
ended at §3.8. The three locked empirical chapter sources
(`chapter5.md` selection, `chapter6.md` structure, `chapter7.md`
cardinality) and the Discussion + Conclusion content had not yet
been integrated into the manuscript. The program executed the
remaining writing in this order:

- Stages 7a–7d: integrate the three locked empirical chapters
  into a single consolidated Chapter 4 with sections §4.2
  (Counterexample selection), §4.3 (Counterexample structure),
  §4.4 (Counterexample cardinality), under the deep-nested
  §4.X.Y.Z numbering scheme Chapter 3 had already committed to.
  Stage 7a was a read-only audit producing a scoping report
  (`thesis/notes/ch4_integration_audit.md`) and a Discussion
  outline (`thesis/notes/ch5_outline.md`) that gave every Ch4
  forward-pointer a stable §5.X landing pad.
- Stage 7e: global figure/table renumbering across Chapter 4
  (Figure 4.1 through Figure 4.9; Table 4.1 through Table 4.18),
  plus §4.3 hyphenated-form cleanup and rels-file deduplication.
- Stages 8a/b/c: draft Chapter 5 (Discussion) against the §5.X
  outline at `thesis/notes/ch5_outline.md`. Chapter 5 covers
  §5.1 (claim verdicts against §1.10.2), §5.2 (methodological
  implications for LLM-AHD evaluation), §5.3 (cross-axis
  design-space synthesis), §5.4 (limitations spanning the
  empirical work), §5.5 (future-work directions).
- Stage 9: draft Chapter 6 (Conclusion) as a brief 5-paragraph
  closing chapter (~530 words).
- Stage 10: final consistency sweep — global cross-reference
  validation, Sense-A retirement re-verification, rels-file
  check, docx validity. Surfaced and fixed 3 substantive issues
  (2 `chapter-7` text leftovers in §5.2.2 prose carried over
  from chapter7.md, 1 `§4.4.1` reference in §5.3 pointing at an
  unlabeled subsection). Defense-readiness confirmed at scope.

Reason. The pre-Stage-7 manuscript did not contain the empirical
results, the discussion, or the conclusion — none of the work
that makes the thesis defensible was in the manuscript itself.
The locked empirical chapter sources had been kept as standalone
Markdown files while Chapters 1–3 were drafted; the
consolidation deferral was deliberate because Chapter 3
methodology needed to be settled before the empirical chapters
could reference it. With Chapter 3 stable by Stage 6, the
consolidation was unblocked.

Final manuscript state. 6 chapters (Introduction + Ch1
Background + Ch2 Conceptual Framework + Ch3 Methodology + Ch4
Experiments and Results + Ch5 Discussion + Ch6 Conclusion).
41,321 words. 143 numbered headings. 9 figures (all in Ch4,
numbered Figure 4.1–Figure 4.9). 18 tables (all in Ch4,
numbered Table 4.1–Table 4.18). Sense-A retirement closed
manuscript-wide (the 2026-05-14 retirement decision is now
fully reflected in every chapter of the manuscript — zero hits
across 22 forbidden terms). Cross-references validated globally;
rels file clean (19 unique entries); docx structurally valid
(`pandoc -f docx -t plain` round-trips clean).

Methodological notes from the program.

1. The custom `unpack.py`/`pack.py` docx pipeline built in
   Stage 6 was reused for every subsequent stage. Stock pandoc
   was avoided because its docx output rewrites style metadata;
   the custom converter preserves the manuscript's existing
   Calibri-blue headings (`Heading1`/`Heading2`/`Heading3`/
   `Heading4` `pStyle` annotations with `color="4f81bd"`) and
   Cambria-`sz="24"` body runs.

2. Pre-stage discipline ("always re-unpack from the pre-stage
   state, not from in-progress state") was codified after the
   Stage 7c duplicate-§4.3 incident. Every subsequent stage
   took a `pre_stageNN` backup of `Thesis Chaps.docx` before
   editing and reverted to it on any error. Backups are
   preserved at
   `thesis/writing/Thesis Chaps.pre_stage{7d,7e,8a,8b,8c,9,10}.docx`.

3. The "data narrative stays in §4.X, methodological reading
   goes to §5.2" pattern was applied to §4.3.4.4 (cross-batch
   reproducibility) and §4.4.6.4 (cross-time-window stability).
   The empirical observation lives in the data section; the
   broader-implications discussion is forward-pointed to the
   Discussion chapter. This pattern protects against the data
   sections growing into discussion-density and against the
   Discussion floating free of its empirical anchors.

4. Discussion-chapter discipline. (a) Verdicts in Chapter 6
   must mirror Chapter 5's verdicts in qualification strength
   — Stage 9 enforced this with explicit citation of §5.1.1 /
   §5.1.2 / §5.1.3 in each Conclusion paragraph; (b) no new
   material in the Conclusion (every claim traces to Chapter 5
   or earlier); (c) discussion sections cite empirical anchors
   precisely rather than paraphrasing the findings loosely.

5. Cross-reference renumbering was mechanical for in-prose §X.Y
   references but required substantive prose work for cross-
   chapter framing. §6.4.4 (Ch5→Ch6 cross-batch reproducibility
   narrative) became §4.3.4.4 (§4.2-vs-§4.3 internal
   reproducibility). §7.7.2 ("From Chapter 7 to Chapter 8")
   became §4.4.7.2 ("From §4.4 to Chapter 5"), with the four
   Ch8 forward-pointers in the original consolidated into three
   Ch5 §5.X landings. The mechanical-to-substantive split was
   the Stage 7a audit's key scope-realism contribution.

6. Sense-A retirement closure is now defense-grade. The
   2026-05-14 decision retired the regime / `h_strong` / two-
   regime taxonomy from the thesis vocabulary; the manuscript-
   writing program propagated that retirement into Chapters 4,
   5, and 6 as they were drafted. Stage 10 verified zero hits
   manuscript-wide for 22 Sense-A forbidden terms. Sense-B
   "regime" usage (`single-shot regime`, `compound regime`,
   `regime-dependent rank-ordering`, `evaluation regime`,
   `regime-conditional`) is preserved as load-bearing technical
   vocabulary.

Reference.

- `thesis/writing/Thesis Chaps.docx` (the manuscript;
  defense-ready at scope).
- `thesis/notes/ch4_integration_audit.md` (Stage 7a scoping
  report; preserved as historical artifact).
- `thesis/notes/ch5_outline.md` (Stage 7a discussion outline;
  preserved as historical artifact).
- `scripts/office/unpack.py`, `scripts/office/pack.py`
  (Stage-6 docx pipeline, reused throughout).
- Stage-by-stage backup files at
  `thesis/writing/Thesis Chaps.pre_stage{7d,7e,8a,8b,8c,9,10}.docx`
  (rollback paths preserved).
- 2026-05-14 entry of this log (the Sense-A retirement decision
  this program propagated through the manuscript).

Alternatives considered and rejected.

- Flat-numbering Option B for Chapter 4 (e.g., §4.1 Selection,
  §4.2 Structure, §4.3 Cardinality without §4.X.Y nesting).
  Rejected: Chapter 3 had already committed to deep-nested
  §4.X.Y.Z references in its prose (e.g., §4.2.2.1 pool
  composition references). Switching to flat numbering would
  have required re-editing Chapter 3 — out of scope for the
  manuscript-writing program.
- Drafting Chapter 5 prose before Stage 7a's outline. Rejected:
  the locked Ch4 forward-pointers (especially the 9 Chapter-8
  forward-pointers in chapter7.md's §7.6 and §7.7) needed
  stable §5.X landing pads; outlining first as section-headings-
  plus-bullets resolved this without committing to Ch5 prose
  before the integration scope was clear.
- Incorporating §3.6's preliminary repair experiment into
  Chapter 4 as a §4.1 negative-result section. Rejected: §3.6
  is methodology (the failure mode the §3.4 split discipline
  is engineered to detect), and Chapter 5 §5.1.3's claim 3
  verdict already cites §3.6 as the negative-result evidence
  for the methodology. Moving §3.6 into Chapter 4 would have
  duplicated the citation without adding empirical content.

---

**2026-05-14 — Two-regime conceptual frame retired; `h_strong` removed from thesis vocabulary.**

Decision. The two-regime structure (large-headroom vs
fine-tuning) and the heuristic name `h_strong` are retired
from the thesis. The 2026-04-24 narrowing of spine commitment
#2 retained `h_strong` as a "defined-but-unrealized concept"
and the two-regime structure as a "conceptual frame in
chapter 3"; this entry retires both. The preliminary
single-pass repair experiment is preserved as the
negative-result motivation in Chapter 1 §1.4; no name is
given to the heuristic the experiment was meant to produce.
Empirical chapters 5, 6, 7 operate on `h_eoh` alone, which
is already the case.

Reason. On reflection, the regime taxonomy did no real
conceptual work in the three-axis design-space argument
that the thesis defends. The empirical chapters never used
the regime distinction to interpret a finding. Retaining
`h_strong` and the two-regime vocabulary added reader
cognitive load without payoff. The preliminary-experiment
motivation in Chapter 1 §1.4 is preserved without the
taxonomy: naive single-pass repair did not generalize,
therefore the variables that matter are which
counterexamples, what structure, and how many.

Scope of this entry. Sense-A vocabulary is retired:
`h_strong`, `large-headroom regime`, `fine-tuning regime`,
`two-regime structure`, `regime contrast`, `regime-(a)`,
`regime-(b)`, `both incumbents`, `two canonical incumbents`.
Sense-B "regime" language is unchanged and remains
load-bearing: `regime-dependent rank-ordering` (Ch5 §5.4),
`single-shot regime` / `compound regime` / `evaluation
regime` (Ch5, Ch6, Ch7), and the statistical-defensibility
`three regimes` of Ch7 §7.7.1 limitation 2
(large-and-defended / null-by-test-construction /
large-and-inconclusive).

Downstream consistency.
- `00_thesis_spine.md` — commitment #2 rewritten; the
  "What this thesis does not claim" two-regime bullet
  deleted.
- `05_glossary.md` — `h_strong`, `Regime-(a)`, and
  `Regime-(b)` entries deleted; `Incumbent` and `h_eoh`
  entries updated; `Regime-dependent ranking` entry
  unchanged.
- `03_thesis_outline.md` — chapter 3, 4, 5, 6, 7
  paragraphs simplified to remove regime vocabulary and
  `h_strong`; the chapter 4 paragraph references "the
  preliminary single-pass repair experiment" without a
  name for its intended output.
- `02_current_state.md` — `h_strong`-related checklist
  items removed.
- `04_experimental_matrix.md` — `h_strong` planning rows
  retired or rewritten.
- Locked empirical chapters (chapter5.md, chapter7.md),
  AGENTS.md, `thesis/code/incumbents.py`, and design docs
  are scheduled for separate edits in later stages of this
  retirement; the present entry documents the policy that
  governs those subsequent edits.

Alternatives considered and rejected.
- Retain `h_strong` as the name of the failed-to-be-produced
  artifact. Rejected: introducing a name for a thing that
  does not exist forces the reader to learn vocabulary with
  no payoff, and Ch1 §1.4 reads fine describing the
  experiment without a name.
- Retry the standardized repair pass with a re-specified
  procedure. Rejected: this was already considered and
  rejected in the 2026-04-24 entries (a re-specified repair
  pass would itself be a new thesis axis — repair-pass
  design — outside the current three-axis scope). Re-opening
  the decision now would also require reopening locked
  empirical chapters that reference the scope narrowing.

Reference.
- `thesis/docs/00_thesis_spine.md` (commitment #2,
  non-claims list).
- `thesis/writing/chapter1_draft.md` §1.4 (preliminary
  repair experiment, untouched by this entry but
  forthcoming Stage 4 edits drop the `h_strong` name from
  the same paragraph).
- Decisions-log entries 2026-04-20 "Two canonical
  incumbents", 2026-04-24 "Spine commitment #2 unlocked and
  narrowed to `h_eoh`-only empirical scope", and the two
  2026-04-24 chapter-narrowing entries (Entry A "Chapter 6
  runs on `h_eoh` only" and the preceding "Chapter 5
  operates on `h_eoh` only"). All historical and unchanged.

---

**2026-05-05 — Chapter 7 §12 cross-`k` matched-pair coordinate alignment locked: slot-aligned, not nested-prefix.**

Decision. Cross-`k` matched-pair statistics in chapter 7 are
slot-aligned, not nested-prefix. The seed-derivation namespace
in §5.2 (`ch7:set:strat:k{N}:set{idx}`) produces independent
CounterexampleSets at different `k` values that share the slot
index `set_index` but not the underlying instance content:
`(set_index=5, k=2)` is an independent draw under its own
seed, not an extension of `(set_index=5, k=1)` plus one
additional instance. Cross-`k` matched-pair statistics compare
proposal-quality distributions across cells whose evidence
shares the slot label as a coordinate device but whose
underlying counterexamples are different at each `k`.

Reason. The nested-prefix alternative would conflate "the
effect of adding one more counterexample to the prompt" with
"the LLM's response to the same anchor instance shown twice in
different contexts" — neither is what claim #3 measures. The
slot-aligned interpretation measures what claim #3 actually
targets: how the proposal-quality distribution shifts as a
function of `k`, with each `k` cell measuring a fresh
independent draw under the same selection strategy.

Alternatives considered and rejected.
- Nested-prefix interpretation: `(set_index=5, k=2)` extends
  `(set_index=5, k=1)` with one additional draw under the same
  set_seed. Rejected on the conflation argument above; the
  resulting matched-pair statistic would mix two different
  effects.
- Doing nothing and letting the literal §5.2 namespace decide
  implicitly. Rejected on the grounds that §12's
  matched-pair-statistic specification is load-bearing for the
  chapter's reported numbers and deserves explicit
  disambiguation in the design doc.

Reference.
- `thesis/writing/chapter7_design.md` §12 (amended in this
  commit), §5.2 (the underlying namespace), §6.1 / §7.1
  (matched-pair statistic definitions).
- The CounterexampleSet artifact's `set_index_alignment` block
  at `thesis/artifacts/chapter7_counterexample_sets.json`
  (commit `3ee9b72`) documented the implementation's
  resolution; this entry locks it as a design choice.

---

**2026-05-05 — Chapter 7 transport authorized: Vertex AI for primary batch and forward, with `reasoning_effort="medium"` mapped to `thinkingBudget=10240` at the transport layer.**

Decision. Chapter 7's primary, validation, and any further
empirical batches run on Gemini 2.5 Pro served via Vertex AI.
The model and its core parameters (`temperature=1.0`,
`max_output_tokens=32768`) remain identical to ch5/ch6
production. The Vertex-specific `thinkingBudget=10240` mapping
for `reasoning_effort="medium"` is documented as a
transport-level specification per
`thesis/code/chapter5/llm_client.py::_vertex_thinking_budget`.

Reason. The direct Gemini API returned HTTP 429
RESOURCE_EXHAUSTED ("Your prepayment credits are depleted")
across all 10 cells of the chapter 7 calibration-probe first
attempt. Vertex AI serves the same `gemini-2.5-pro` model and
ran the same calibration probe cleanly (commit `145b2e5`); all
10 cells sanitized OK and returned `finish_reason="STOP"`.
Spine architectural commitment #4 locks the model identity, not
the transport, so authorizing Vertex at the chapter-design
level does not require a spine amendment.

Alternatives considered and rejected.
- (a) Topping up direct-Gemini prepayment credits and running
  primary batch on the direct API. Rejected: structural billing
  change makes Vertex the production path going forward;
  reverting to direct-Gemini for one chapter would introduce a
  transport asymmetry across ch5/ch6/ch7 worse than the
  asymmetry already created by ch6's verification probes having
  used Vertex.
- (b) Splitting primary batch across both transports. Rejected:
  introduces an uncontrolled confound at the transport layer.

Note on chapter 6. The chapter-6 verification probes also ran
on Vertex (per the 2026-05-05 ch7 conversation's confirmation);
that fact was not recorded as a decisions-log event at the time
of ch6 work and is a separate retroactive-cleanup task outside
this entry's scope. A future ch6-transport retroactive entry
would record what was already locked in ch6's batch
infrastructure on its own date and would close the parallel
asymmetry to the ch6 master-seed backfill (commit `1defbc3`).

Reference.
- `thesis/writing/chapter7_design.md` §3.5 (amended in this
  commit).
- Calibration-probe artifact
  `thesis/artifacts/chapter7_calibration_probe.json` (commit
  `145b2e5`), specifically the `provider_fallback` block.
- `thesis/code/chapter5/llm_client.py::_vertex_thinking_budget`
  for the mapping function.
- Decisions log 2026-04-21 "Primary LLM swapped from
  `gemini-3.1-pro-preview` to `gemini-2.5-pro`" — the
  model-level lock that this entry's transport-level lock sits
  beneath.

---

**2026-05-05 — Chapter 7 §5.1 unique-CounterexampleSet accounting corrected: 80 stratified sets and 4 deterministic sets, shared between L1 and L2 cells at the same `(strategy, k, set_index)`.**

Decision. The §5.1 arithmetic was wrong: the chapter generates
**80 unique stratified CounterexampleSets** and **4 unique
deterministic CounterexampleSets**, totaling **84 unique sets**
used by the 14 primary cells. L1 and L2 cells at the same
`(strategy, k, set_index)` share the same CounterexampleSet
because the set is a function of selection (not of structural
level), and the §5.2 seed namespace correctly has no level
component.

Reason. Mechanical correction. The original arithmetic
double-counted by treating L1 and L2 instantiations of the same
`(strategy, k, set_index)` as separate sets when they are not.

Reference.
- `thesis/writing/chapter7_design.md` §5.1 (amended in this
  commit).
- The CounterexampleSet artifact at
  `thesis/artifacts/chapter7_counterexample_sets.json`
  (commit `3ee9b72`) was generated with the correct (84) count;
  the artifact's `level_sharing` block already documents this.
  This decisions-log entry brings the design-doc text into
  alignment with what the implementation produced.

---

**2026-05-05 — Chapter 7 cardinality range locked: `k ∈ {1, 2, 4, 8}` at Level 1 and `k ∈ {1, 2, 4}` at Level 2; the L2 cap at `k=4` is forced by the locked N=60 trace rendering rule under Gemini 2.5 Pro's input ceiling.**

Decision. Chapter 7 sweeps cardinality at L1 across `k ∈ {1, 2, 4, 8}`
and at L2 across `k ∈ {1, 2, 4}`. The L2 upper bound is asymmetric to
the L1 upper bound; the cardinality × structure characterization is
therefore bounded to the small-`k` regime and named as such in the
chapter's claim formulation and limitations.

Reason. The 2026-04-25 N=60 lock budgets the Level-2 trace portion at
~624K worst-case prompt tokens at `k=4` (~60% of Gemini 2.5 Pro's
1,048,576-token input ceiling, ~40% headroom). Linear scaling at the
locked N=60 puts the trace portion at `k=8` worst-case at ~1,248K
tokens, which exceeds the input ceiling before the L1 block (incumbent
code, reference code, k=8 instance summaries, framing) is added. `k=6`
projects to ~936K trace tokens — feasible on the trace portion alone
but with the L1 block on top sits within ~10% of the ceiling, which
the chapter's calibration probe (`chapter7_design.md` §18.1) treats as
insufficient headroom. The L2 range is therefore capped at the largest
`k` that the N=60 lock unambiguously supports: `k=4`. The L1 upper
bound at `k=8` is well within feasibility: the L1 block at `k=4` is
~3K tokens per the ch5 calibration, scaling roughly linearly with
`k`, putting `k=8` at ~6K tokens — three orders of magnitude below
the ceiling. (Budget arithmetic verbatim from `chapter7_design.md`
§3.8.)

Alternatives considered and rejected.
- (a) Re-derive the N=60 rendering rule at variable N for upper-`k`
  (e.g., shrink N on the L2 column at `k=8` to fit the same
  trace-token budget). Rejected: the rendering rule is a chapter-6
  lock, and any change is a decisions-log event that re-invalidates
  ch6's L2-conditional findings — chapter 6's primary claim
  (selection × structure interaction at L2 vs L1) is conditional on
  the N=60 distortions named in ch6 §6.7.1, and a variable-N rule
  changes the distortion profile across the L2 column non-uniformly,
  which would then propagate back into ch6 reproducibility. The
  chapter 6 lock holds.
- (b) Shrink the L2 range to `k ≤ 6` and accept an even tighter cap.
  Rejected: not meaningfully different from a `k=4` cap given the
  L1-block-on-top headroom shrink at `k=6`; `k=6` lands within the
  calibration probe's ~10% headroom threshold (§18.1) which the
  chapter 7 design treats as a re-derivation trigger, defeating the
  point of stretching.
- (c) Run the upper-`k` end at L1 only. Accepted — this IS the
  chosen design.

Reference.
- `thesis/writing/chapter7_design.md` §3.8 (cardinality axis
  specification with budget arithmetic), §18.1 (calibration probe
  with the ~10% headroom threshold), §16.2 (token-budget
  verification at L2).
- Decisions log 2026-04-25 "Chapter 6 Level-2 trace rendering rule
  revised a second time: N=60 rows (head=12, stride=48), calibrated
  against an empirically-measured ~1.04 chars/token ratio" — the
  underlying rendering-rule lock whose budget math forces the cap.
- `thesis/writing/chapter6_design.md` §7.4 — the rendering rule's
  authoritative spec.

---

**2026-05-05 — Chapter 7 lower-boundary convention: at `k=1`, `worst_plus_best` is replaced by `worst_only_at_k1` (the single-instance limit of `worst_plus_best`'s deterministic worst-half component); the substitution is applied at both L1 and L2 cells where `k=1`.**

Decision. The chapter 7 cardinality axis hits a strategy-collapse at
its lower boundary: `worst_plus_best` requires `k ≥ 2` because it
partitions selection into `k/2` worst plus `k/2` best instances. At
`k=1` the partition is undefined. Chapter 7 uses
**`worst_only_at_k1`** — selection of the single largest-gap
counterexample, i.e., the single-instance limit of `worst_plus_best`'s
deterministic worst-half component — as the boundary substitution.
The substitution is named explicitly as a chapter-7-specific
convention rather than a strategy variation; its `k=1` cell is
reported alongside `worst_plus_best`'s `k ∈ {2, 4, 8}` cells on the
cardinality curve for that strategy. The substitution is applied at
both L1 (CH7-05) and L2 (CH7-12) cells where `k=1`.

Reason. The cardinality axis is the chapter's organizing axis, and
the cardinality curve at each strategy needs a defined point at every
`k` value the chapter sweeps. Leaving the `worst_plus_best @ k=1`
cell empty would create an asymmetry in the cardinality-curve plots:
the `stratified_representative` curve has data at `k ∈ {1, 2, 4, 8}`
(L1) and `k ∈ {1, 2, 4}` (L2), but the `worst_plus_best` curve would
skip `k=1`, foreclosing the cross-strategy comparison at the lower
boundary that the cardinality-stability claim
(`chapter7_design.md` §1) is positioned to make. The single-instance
limit of `worst_plus_best`'s worst-half component is the closest
principled extrapolation: at `k=1`, the strategy's defining structure
reduces to "show the LLM the worst-gap instance," which is exactly
what the chapter-5 `worst_only` strategy (chapter 5 design §5.2)
does. The substitution preserves the deterministic property of
`worst_plus_best` (one set, varied LLM seed) and is unambiguous
against any reasonable definition of "the worst-half of a single
instance." `stratified_representative @ k=1` does not face the same
collapse: ch5 design §5.6's proportional-allocation rule
deterministically picks a single stratum at `k=1` (`strong_wins`
first), preserving the strategy's stochastic-set-variation property
at the boundary.

Alternatives considered and rejected.
- Drop `worst_plus_best` from the `k=1` row entirely (no boundary
  substitution). Rejected: leaves the `k=1` cardinality-curve point
  asymmetric across strategies — `stratified_representative` has a
  `k=1` measurement but `worst_plus_best` does not, which forecloses
  the cross-strategy comparison at the lower boundary.

Reference.
- `thesis/writing/chapter7_design.md` §3.8 (boundary cases and the
  substitution rule), §4.1 (the `CH7-05 worst_only_at_k1 L1 k=1` and
  `CH7-12 worst_only_at_k1 L2 k=1` cells in the primary matrix).
- `thesis/writing/chapter5_design.md` §5.2 — the underlying
  `worst_only` strategy specification whose single-instance limit
  the substitution invokes.

---

**2026-05-05 — Chapter 7 `dev` split activation as read-only post-hoc evaluation: `dev` is scored once at chapter close on every accepted validation step's proposal and on each primary cell's highest-Δ_step proposal; `dev` does not drive any in-chapter decision.**

Decision. Chapter 7 introduces `dev` scoring as a post-hoc evaluation
pass executed once at chapter close. The scoring is applied to (a)
every accepted proposal in the chapter's validation trajectories —
typically a small subset of the 210 validation calls — and (b) the
highest-Δ_step proposal from each of the 14 primary cells. `dev`
does not participate in any in-chapter decision: not in selection,
not in trajectory acceptance, not in cell ranking. `test_ood`
remains untouched per the spine.

Reason. The chapter's spine commitment to claim #3 — "comparative
counterexample learning exhibits a characteristic overfitting mode
that scales with counterexample set size and with overlap between
the evidence-providing set and the evaluation set" — is
operationalized in chapter 7 as the relationship between the
`train_step`, `train_gate`, and `dev` evaluation curves as a
function of `k`. `train_step` and `train_gate` are already used by
ch5/ch6; the chapter-7 contribution adds `dev` as the third,
most-disjoint reference point. Computing `dev` only on the chapter's
strongest proposals (rather than every proposal in every cell) keeps
score-cache fills proportional to the analytical payoff: the
cardinality-curve plots use `dev` as a third generalization curve
rather than as a primary metric, and computing it across all 840
primary cells would multiply score-cache fills without an
empirical-claim payoff. The `dev` activation is post-hoc rather than
in-loop because using `dev` to drive any in-chapter decision (e.g.,
trajectory acceptance) would compromise its role as a held-out
generalization reference.

Reference.
- `thesis/writing/chapter7_design.md` §3.3 (splits — `dev` as
  chapter-7 specific addition), §6.3 (`Δ_dev` as the chapter-7
  generalization extension), §18.8 (the post-hoc `dev` scoring
  pass).
- Decisions log 2026-04-20 "Thesis five-subset split defined" —
  the underlying split discipline (`train_select` / `train_step` /
  `train_gate` / `dev` / `test_ood`).
- `thesis/docs/00_thesis_spine.md` claim #3 — the generalization
  claim whose `dev` scoring is positioned to defend.

---

**2026-05-05 — Chapter 7 budget acknowledgment: ~$465–500 expected total spend (~1.6× ch6's actual ~$300), explicitly acknowledged by the user before the design doc lands and primary-batch implementation begins.**

Decision. Chapter 7's expected spend is ~$465–500 across 14 primary
cells (840 calls) + 14 cells × 3 trajectories × 5 steps validation
(210 calls) + ~10 calibration calls — ~1,060 LLM calls total.
Per-class breakdown: L1 cells ≈ $10, L2 cells ≈ $450, calibration ≈
$5. This crosses ch6's actual spend (~$300) by roughly 1.6×, driven
by chapter 7's six L2 cells (vs. ch6's four). The user has
acknowledged this overage prior to design-doc landing.

Reason. Chapter 7 inherits ch6's L2-cell-per-call cost profile
(~$1.00/call, dominated by the ~620K input tokens of the locked
N=60 trace block at `k=4`) and scales the cell count by the
cardinality axis (3 L2 `k` values × 2 selection strategies = 6 L2
cells, vs. ch6's 1 `k` × 2 strategies × 2 levels = 2 L2 cells where
the structure axis varied). The 1.6× cost ratio is a direct function
of the number of L2 cells, not of any chapter-7 procedural choice.
Recording the budget as a pre-implementation lock is precedent-
aligned with chapter 5's 2026-04-23 primary-batch entry, which also
recorded the expected spend (~$24) before the batch launched. The
chapter-6 ~$300 baseline used here corresponds to the user's
report in the 2026-05-05 ch7 scoping conversation, which corrected
the prior $59 brief figure (carried into the chapter-7 scoping
report at commit `729d6e4`) to the actual ch6 spend.

Reference.
- `thesis/writing/chapter7_design.md` §4.3 (per-class cost
  breakdown), §8.4 (total budget summary).
- Chapter 5 cost actuals: `thesis/docs/04_experimental_matrix.md`
  chapter 5 budget table (~$27 / ~11 hours).
- Chapter 7 scoping report `thesis/writing/chapter7_scoping.md`
  (commit `729d6e4`) §5 — the lower-bound estimate (~$140) the
  scoping conversation later corrected against the ~$300 ch6
  actual.

---

**2026-05-05 — Chapter 7 master seed and namespace locked: `MASTER_SEED_CH7 = 20_260_505`, namespace prefix `ch7:`.**

Decision. Chapter 7 uses an independent master seed
`MASTER_SEED_CH7 = 20_260_505` with namespace prefix `ch7:` for all
sampling reproducibility. The full namespace structure
(per `chapter7_design.md` §5.2):

- `ch7:set:strat:k{N}:set{idx}` — `stratified_representative` set
  generation, `idx ∈ [0, 20)`
- `ch7:llm:strat:k{N}:set{idx}:seed{s}` — stratified-cell LLM seeds,
  `s ∈ [0, 3)`
- `ch7:llm:wpb:k{N}:seed{s}` — `worst_plus_best` LLM seeds,
  `s ∈ [0, 60)`
- `ch7:llm:wo1:seed{s}` — `worst_only_at_k1` LLM seeds,
  `s ∈ [0, 60)`
- `ch7:traj:set:{cell}:traj{t}:step{i}` — trajectory pool-rebuild
  set seeds
- `ch7:traj:llm:{cell}:traj{t}:step{i}` — trajectory LLM seeds

Reason. Disjoint seed namespaces between chapters keep each
chapter's sampling reproducibility independent of the others. This
is the same convention chapter 6 used (`MASTER_SEED_CH6 =
20_260_424`, namespace prefix `ch6:`, locked in chapter 6 design
§13). The chapter-7 namespace's `set_index` numbering is shared
across `k` values within a strategy, which is what the §12
within-coordinate matched-pair statistics require: a coordinate at
`set_index=5` must refer to the same set across `k ∈ {1, 2, 4, 8}`
for the cross-`k` matched-pair difference to be defined.

Reference.
- `thesis/writing/chapter7_design.md` §5.2 (full namespace
  specification), §12 (coordinate definitions and the cross-`k`
  numbering requirement).
- `thesis/writing/chapter6_design.md` §13 — the precedent
  (`MASTER_SEED_CH6 = 20_260_424`, namespace prefix `ch6:`).

---

**2026-05-02 — Chapter 6 train_select shown-vs-unshown decomposition entry. Diagnostic re-analysis tested whether the chapter's catastrophe-asymmetry interaction is concentrated on the four counterexamples shown to the LLM (instance-specific hyper-fitting) or holds uniformly across the train_select pool. Finding type 1 (uniform); §6.3.5 and §6.6.1 amended accordingly.**

Records that during cold-read review of the completed chapter,
a possible mechanistic gap was identified: §6.6.1's "frames
failure modes the LLM is being asked to repair" wording carried
an instance-specific hyper-fitting connotation that had not been
directly tested.

The pre-flight (no commit) revealed the originally-scoped
analysis (Δ_step decomposition into shown vs. unshown) was
degenerate — train_step is fully disjoint from train_select; no
shown instances live in train_step. The substantive analog was
a train_select decomposition: each proposal scored against all
30 train_select instances, with the per-proposal Δ vs `h_eoh`
decomposed into Δ_select_shown (mean over the 4 counterexamples
the LLM saw) and Δ_select_unshown (mean over the 26 it did not).

Score-cache pre-flight measured 1.52% hit rate (90 of 5,940
analysis-grid pairs). Full cache fill at 32-way parallelism
completed in 13.3 minutes (5,850 pairs at ~4 sec single-thread,
7.3 pairs/sec parallel). My initial 5-pair timing sample had
been catastrophically unrepresentative — projected 93 minutes
single-thread; actual single-thread rate would have been ~37
hours. The parallel wrapper was the load-bearing intervention.

Analysis (Analyses P–S, `_shown_vs_unshown_analysis.md`) produced
**finding type 1 (uniform)**: per-cell shown and unshown means
agree within less than 1 bin in every cell; catastrophe rates
at threshold −50 differ by at most one record across the two
decompositions; cross-strategy bootstrap interaction CIs on both
Δ_select_shown (+76.50 [+8.37, +156.31]) and Δ_select_unshown
(+76.14 [+7.04, +151.67]) exclude zero with nearly identical
point estimates. Sanity-check Δ_select_full sits in the same
ballpark as the chapter's existing Δ_step interaction CI
(+76.97 [+8.94, +155.04]; verification Analysis G), confirming
train_select and train_step show essentially the same
interaction shape.

Integration: one paragraph appended to §6.3.5 reporting the
decomposition's headline; §6.6.1 paragraph 2 rewritten to drop
the instance-specific over-fitting language and replace it with
representative-comparison-base mechanism (the surrounding
counterexamples concentrate on failures the LLM has no
representative comparison set against which to check itself).
The regularizer-vs-destabilizer reading is preserved. §6.6.3
and §6.7.1 require no edits — finding type 1 forecloses an
objection without introducing a new limitation, and §6.6.3's
per-pair r ≈ 1.000 between Δ_step and Δ_gate is independent
of train_select.

Three commits in order:

- `5bba5d0` — cache fill (5,850 train_select scorings via the
  multiprocessing wrapper; 32 workers; 13.3 min wall-clock)
- `17e2665` — train_select shown-vs-unshown analysis artifact
  + script (Analyses P–S; finding type 1)
- `53165a3` — chapter prose integration (§6.3.5 paragraph +
  §6.6.1 paragraph 2 rewrite + 8 claims-table rows)

Final chapter state: ~9,408 words across 7 sections, 130
claims-table rows. The catastrophe-asymmetry interaction is
now defended on three disjoint splits (train_step via
verification Analysis G, train_gate via verification Analysis
J, and train_select via the decomposition above). The chapter's
primary claim is unaffected; the §6.6.1 mechanistic
interpretation is sharpened from "instance-specific hyper-fit"
to "no representative comparison base" — a more defensible
reading consistent with the data.

Reference. The chapter prose completion entry from this date
(commit `1a76289`) declared the chapter complete; this entry
amends that with the train_select-validation context. The
chapter is still complete; the workstream documented here was
a confirmatory check rather than a new contribution. Chapter 7
design remains the next workstream.

---

**2026-05-01 — Chapter 6 prose completion entry. Chapter 6 drafted across all seven sections; chapter complete and reviewed. Chapter 7 design is the next workstream.**

Records that chapter 6 prose drafting is complete. Eight
drafting commits in order plus one final consistency pass:

- `542934c` — §6.2 Setup (chapter file created; conventions locked)
- `4d27398` — §6.2 small cleanup edits (drop bias mention; verify §5.3.1 ref)
- `f2899e8` — §6.3 Primary-batch results (5 subsections, ~10pp)
- `4c29218` — §6.4 Validation-batch results (4 subsections + verdicts, ~5pp)
- `5c1f706` — §6.5 Argmax-equivalence rate across batches (~1.5pp)
- `41b2178` — §6.6 Discussion (3 subsections, ~5pp)
- `b07a210` — §6.7 Limitations and forward view (~3pp)
- `7b383b7` — §6.1 Introduction (~1.5pp; drafted last)
- `0b05f72` — final consistency pass (4 surface fixes)

Final chapter stats: ~9,185 words across 7 sections, 6
figures, 13 tables. Companion `chapter6_claims_table.md`
records 123 quantitative or substantive claims with source
artifact pointers. Forbidden-language sweeps (six retired
patterns) clean across the full document; cross-references
to design-doc and decisions-log entries verified consistent.

Chapter 7 design is the next workstream. The spine names
chapter 7 as the cardinality axis of the three-axis design
space; no preliminary design or analysis work has been done.
Chapters 5, 6, and 7 are intended to carry the spine's
three-axis framework incrementally (selection, structure,
cardinality), with selection and structural enrichment held
at chapter-5 and chapter-6 configurations during chapter 7's
cardinality work.

Reference. Chapter prose at `thesis/writing/chapter6.md`;
claims table at `thesis/writing/chapter6_claims_table.md`;
chapter outline at `thesis/writing/chapter6_outline.md`
(commit `de9bd79`); the chapter's empirical artifacts
(verification, post-validation, plots) under
`thesis/results/chapter6_primary_batch_gemini/` and
`thesis/results/chapter6_validation_batch_gemini/`.

---

**2026-05-01 — Chapter 6 §1 secondary-metric paragraph demoted to honest reporting (no expectation about trace effect direction on argmax-equivalence rate). Validation data does not reproduce the primary-batch L1→L2 reduction at n=15. §14 adds a limitation on partial ch5→ch6 L1 reproducibility for `worst_plus_best`.**

Decision. Two coupled changes to `chapter6_design.md`:

(a) §1's secondary-metric paragraph rewritten to **report
rather than predict** the argmax-equivalence direction. The
paragraph now states the primary-batch reductions
(`stratified_representative` 13.3% → 10.0%; `worst_plus_best`
23.3% → 16.7%) and the validation-batch non-reproduction at
n=15 (strat L1=L2=13.3%; wpb L2=20.0% > L1=13.3%) side by
side. The chapter's prior expectation that the trace would
"modestly reduce argmax-equivalence rate within each
selection strategy" is retired; the metric is now reported
as a continuity-with-ch5 observation across two sampling
regimes rather than a prediction about trace effect
direction.

(b) §14 adds a limitation bullet on ch5/ch6 L1
reproducibility: ch6 `worst_plus_best@L1` validation
trajectory mean (+7.32) is ~3 bins above ch5's
(+4.31), while `stratified_representative` reproduces ch5
within 0.40 bins. Possible sources (backend drift over
months, time-of-day variance, seed-namespace variation at
n=3) are listed without attribution because n=3 per cell
makes attribution ungrounded.

Why this revision. Validation Analysis L (commit 7f6236f)
returned strat L1=L2=13.3% and wpb L1=13.3%, L2=20.0% on
`rejected_argmax_equivalent` rates. The primary-batch
verification (Analysis C, commit e7654e5) showed small
reductions (13.3%→10.0%, 23.3%→16.7%); validation does not
replicate. Under `worst_plus_best`, the direction inverts (L2
higher than L1). At n=15 per cell the validation difference
is within the sampling-noise floor, and the chapter prose
should not claim a reduction it cannot defend.

Why now (third §1 edit in three days). The §1 paragraph has
been edited in three task cycles: (1) main-effect →
interaction (commit 1237531); (2) generic-interaction →
tail-specifically with bootstrap evidence (commit 7763379);
(3) this entry's secondary-metric demotion. Each edit was
driven by new analytical evidence — the verification
analysis, the inferential analysis, the validation analysis.
The chain of edits is honest: as more evidence accumulated,
the chapter's claim sharpened from coarse to specific to
honest-about-what-it-does-not-claim. Append-only logs
preserve the trail.

Why the §14 reproducibility note. Analysis O surfaced the
~3-bin gap between ch5 wpb trajectory mean (+4.31) and ch6
wpb L1 trajectory mean (+7.32). This does not affect the
chapter's within-batch L1-vs-L2 measurement, but it is worth
naming so a future reader investigating ch5→ch6
comparability sees the gap acknowledged rather than hidden.
Possible causes (backend drift, time-of-day, seed namespace)
are listed without attribution because n=3 per cell makes
attribution ungrounded.

What survives unchanged. Claims 1, 2, 3, 5 from the
validation analysis are SUPPORTS. The interaction framing
(§1 stronger-form), the tail-behavior framing (§11.1b), the
catastrophe-rate emphasis, and the §14
metric-dependence-of-defensibility bullet are all preserved
as-is. The demotion is targeted to the secondary-metric
paragraph only.

Spine impact: none. The spine's defended claim #2 is
unchanged. The chapter's primary structural-enrichment claim
is unchanged. The demoted secondary claim was a ch5-mechanism
continuity expectation, not a structural-enrichment claim.

Reference. Validation analysis commit 7f6236f, primary-batch
verification Analysis C (commit e7654e5), the three prior
2026-05-01 entries.

---

**2026-05-01 — Chapter 6 §1 / §11.1 / §14 sharpened to lead with catastrophe-asymmetry framing. The interaction is statistically defended on tail-behavior statistics (mean Δ, catastrophe-rate) and not on central-tendency or rank-order statistics at n=60. Supersedes the framing language in the 2026-05-01 realignment entry that claimed three converging cuts.**

Decision. Three coupled framing changes to `chapter6_design.md`:

(a) §1's stronger-form paragraph extended to name the
tail-behavior / catastrophe-asymmetry framing as the
interaction's most robustly defended form. Median and Cliff's δ
characterizations are explicitly named as directionally
consistent but not statistically distinguished from zero at
n=60.

(b) §1's spine-claim paragraph's "three independent cuts
converge" sentence replaced with language that distinguishes
*directional convergence* (across multiple cuts: cell-level
distribution stats, matched-pair Δ, trace-engagement-class Δ,
catastrophe-rate tabulation) from *statistical defensibility*
(specifically on cross-strategy mean Δ_step CI [+8.94, +155.04],
cross-strategy mean Δ_gate CI [+8.53, +158.66], and
catastrophe-asymmetry tabulation).

(c) §11.1 elevates catastrophe-rate to a co-equal sub-statistic
with cell-level distribution stats (the section becomes "Primary
I — cell-level Δ_step distribution per cell, with catastrophe-
rate tabulation," with two co-equal sub-parts (a) distribution
stats and (b) catastrophe-rate). The catastrophe-rate
sub-statistic is named as the chapter's most statistically
defended characterization of the interaction, with the
distribution stats providing the standard ch5 → ch6 reference
frame.

(d) §14 adds an honest "statistical defensibility of the
interaction is metric-dependent" limitation bullet naming which
statistics defend the interaction at n=60 (mean Δ_step, mean
Δ_gate, catastrophe-asymmetry) and which include zero at this n
(median Δ, Cliff's δ).

Why this sharpening. The inferential analysis (commit e7654e5,
Analysis G) found that the cross-strategy mean Δ_step
interaction CI excludes zero, but the cross-strategy median Δ
and Cliff's δ CIs include zero. The previous §1 language ("three
independent cuts converge") elided this distinction. A reviewer
reading §1 alongside the inferential numbers would correctly
notice the gap; the sharpened framing closes it before the
chapter prose is written.

Why the catastrophe-asymmetry framing specifically. Analysis H
found that under stratified evidence the trace rescues 100% of
L1 catastrophes (11/11); under worst+best evidence the trace
induces catastrophes at 20.4% (vs stratified 10.2%). The mean
Δ interaction CI's exclusion of zero is mechanistically driven
by this catastrophe asymmetry — the wpb cell's heavy-tail
outliers (the −1255 pair, −463, −400) drive the cross-strategy
mean difference. Catastrophe-rate is the metric that captures
this mechanism most cleanly; promoting it from §11.1 sub-bullet
to co-equal sub-statistic reflects what the inferential analysis
actually shows.

Why median / Cliff's δ remain in the metric set. They are
reported because (a) they are the standard ch5 reference frames
and ch6 → ch5 comparability requires them, and (b) their
directional consistency with the mean / catastrophe-rate
statistics is itself supporting evidence even when their CIs
are wide. The chapter does not drop them; it explains explicitly
which subset of metrics defends the interaction at n=60.

Spine impact. None. The spine's defended claim #2 is unchanged;
ch6 still carries the structure half. The sharpening is on what
specifically ch6 contributes — tail-behavior characterization
rather than uniform-shift characterization.

Consequences for the validation batch. The chapter expects
validation's compound-improvement results to mirror the primary
batch's tail-behavior pattern: under stratified, trajectories at
L2 should show fewer catastrophic regressions than at L1; under
wpb, L2 trajectories may show more catastrophic regressions or
comparable rates of induced catastrophe. The validation analysis
task (after that batch runs) should report trajectory-level
catastrophe-rate alongside cumulative Δ_step.

Reference. Verification commit e7654e5; the immediately
preceding 2026-05-01 inferential-analysis decisions-log entry
(this entry supersedes the framing language in the 2026-05-01
realignment entry that claimed three converging cuts; the prior
entry stays unchanged per append-only discipline); the
2026-05-01 realignment entry from commit 1237531; the realigned
§1 / §11.1 / §14 of `chapter6_design.md` after this task's
edits.

---

**2026-05-01 — Chapter 6 inferential analysis: bootstrap CIs on matched-pair statistics, catastrophe-rate measurement, per-instance breakdown, and gate-set matched-pair generalization. Closes the uncertainty-quantification gap on the interaction claim before validation launches.**

Decision. Add four post-hoc analyses (G, H, I, J) to the
verification artifact, with corresponding minimal §11/§14
additions to the design doc. Specifically: bootstrap CIs on
all matched-pair statistics; catastrophe-rate matched-pair
tabulation with sensitivity check; per-instance breakdown of
the matched-pair Δ; matched-pair Δ_gate replication of G with
per-pair step/gate correlation. Method: percentile bootstrap,
10,000 resamples, paired bootstrap for matched-pair statistics
and unpaired bootstrap (per-cell resampling) for Cliff's δ.
Seed locked to `MASTER_SEED_VERIFICATION = 20_260_501`.

Why now. The realigned primary claim (commit 1237531) is a
selection × structure interaction whose statistical
defensibility had not been quantified. n=60 per cell is small
relative to the matched-pair Cliff's δ magnitudes (stratified
+0.11, wpb −0.01); without bootstrap CIs the chapter cannot
defend against "this is sampling noise at this n." The
catastrophe-rate analysis operationalizes the matched-pair
tail asymmetry described qualitatively in the realignment as
a reportable metric. The per-instance and Δ_gate analyses
characterize where the effect lives and whether it
generalizes off `train_step`.

Numerical results from this batch.

- **Per-strategy matched-pair statistics (full 60 pairs):**
  every per-strategy CI on median Δ, mean Δ, and Cliff's δ
  *includes zero* on both strategies. Stratified median Δ
  +2.22 [−0.70, +6.33]; wpb median Δ −0.22 [−5.97, +1.77];
  stratified Cliff's δ +0.11 [−0.09, +0.32]; wpb Cliff's δ
  −0.01 [−0.23, +0.20]. The within-strategy effect at this
  sample size is not statistically distinguishable from zero
  on any of the three statistics.
- **Cross-strategy interaction CI (the chapter's primary
  claim's actual statistical test):** the matched-pair *mean
  Δ* difference excludes zero (+76.97 [+8.94, +155.04]); the
  matched-pair *median Δ* difference includes zero
  (+2.43 [−1.63, +8.68]); the *Cliff's δ* difference includes
  zero (+0.13 [−0.16, +0.43]). The interaction is defended on
  the mean-Δ statistic; the median-Δ and rank-based statistics
  are directionally consistent but not statistically
  distinguished from zero at n=60.
- **Catastrophe rate at threshold = −50:** stratified L1
  18.3%, L2 8.3% (rate halves under L2); wpb L1 10.0%, L2
  20.0% (rate doubles under L2). Matched-pair tabulation
  (stratified vs wpb classes `cat∧cat / cat∧safe / safe∧cat /
  safe∧safe`): 0/11/5/44 vs 1/5/11/43. **Rescue rate**
  (`L1_cat_L2_safe / total_L1_cat`): stratified 100% (11/11),
  wpb 83.3% (5/6); cross-strategy diff +16.7% [0%, +50%], CI
  lower bound at zero. **Induce rate**
  (`L1_safe_L2_cat / total_L1_safe`): stratified 10.2%, wpb
  20.4%; cross-strategy diff −10.2% [−23.9%, +3.6%], CI
  includes zero. Sensitivity check at threshold = −100:
  stratified rescue 100% (10/10), wpb rescue 100% (3/3);
  qualitative direction matches the primary threshold on
  both rescue and induce.
- **Per-instance Δ within matched pairs:** stratified top-5
  instance share of total positive Δ is 20.7% vs the
  proportional baseline 16.7% — not concentration-driven.
  Top-5 indices on stratified: [2, 28, 14, 9, 10]. wpb has
  no positive total per-instance contribution (every
  instance's average per-pair Δ is non-positive); the
  concentration ratio is undefined for wpb.
- **Gate-set replication (Δ_gate matched-pair):** per-strategy
  CIs all include zero (mirrors step). Cross-strategy mean
  Δ_gate difference excludes zero (+77.46 [+8.53, +158.66]),
  same direction as step. Per-pair Pearson correlation
  between Δ_step and Δ_gate is essentially perfect:
  stratified r = +0.9997, wpb r = +0.9999. The pair-level
  effect transfers cleanly to the disjoint gate set.

Why before validation. Validation is designed to test whether
the interaction observed at single-shot persists under
compounding. If the single-shot interaction is itself not
statistically defended, validation tests a claim with no
baseline. Closing the inferential gap on the primary batch is
a prerequisite for validation being interpretable. The
mean-Δ interaction CI excluding zero — and the gate-set
replication of the same — is what the chapter prose can
defend the interaction on; the median and rank-based
interaction CIs are directionally consistent but not
statistically distinguished, and the chapter prose treats
them as supportive rather than carrying.

Spine impact. None. The four analyses are measurement-side;
the spine's defended claims are unchanged.

Reference. The realignment commit (1237531); the verification
analysis (8b225c4); the realigned §1 / §11 / §14 of the
design doc (post-1237531 + this commit's additions);
`thesis/code/chapter6/experiments/inferential_analysis.py`
(this commit).

---

**2026-05-01 — Chapter 6 design realigned to the selection × structure interaction finding from the primary batch verification (commit 8b225c4). Argmax-equivalence rate updated from 0% (script artifact) to 15.8% canonical via the chapter 5 helper.**

Decision. Three coupled changes to `chapter6_design.md`:

(a) **Primary claim restructured** from a structure main effect
("L2 outperforms L1") to a selection × structure interaction
("L2's effect depends on selection strategy"). The new §1
states the chapter expects the trace to improve proposal
quality under stratified evidence and to have null or adverse
effect under concentrated-extreme evidence (`worst + best`).

(b) **§11 metric hierarchy promoted matched-pair within-coordinate
analysis to primary co-metric** (new §11.2) and
**trace-engagement classification to primary auxiliary** (new
§11.3), with the cell-level Δ_step distribution retained as
primary I (§11.1). Trajectory metrics demoted from primary to
auxiliary (§11.7); other metrics shift number but not status.

(c) **Argmax-equivalence rate measurement is locked to the
canonical chapter 5 helper**
`thesis.code.chapter5.analysis.is_argmax_equivalent_to_h_eoh`
(§11.4 + new §14 limitation bullet). The pre-analysis script's
custom reimplementation read 0% on the primary batch; the
canonical helper read 15.8% on the same data. The 15.8%
figure is the authoritative number; the 0% reading was a
measurement-script artifact.

Why this realignment. Verification commit 8b225c4 plus the
different-hash matched-pair analysis (Analysis F) committed
alongside the realignment establish three independent cuts of
the data:

- **Cell-level Δ_step**: stratified_representative Cliff's δ
  +0.11; worst_plus_best Cliff's δ −0.01.
- **Matched-pair median Δ(L2 − L1)**: stratified +2.22; wpb
  −0.22. On the different-hash subset (Analysis F): stratified
  +3.30 (n=58), wpb −0.43 (n=59) — direction confirmed under
  the more conservative subset.
- **Trace-engagement Δ(L2 − L1) by class** on the different-hash
  subset: stratified C +13.04 (n=22), M +42.64 (n=31), A −16.70
  (n=5); wpb C −34.12 (n=23), M −70.68 (n=32), A −11.62 (n=4).
  Citation correlates positively on stratified, negatively on
  wpb — the relationship inverts.
- **Strict argmax-equivalence rate**: 15.8% combined across 240
  records (per-cell strat L1 13.3%, strat L2 10.0%, wpb L1
  23.3%, wpb L2 16.7%). Modest L1 → L2 reduction in both
  strategies. Comparable to chapter 5 §5.2.3 Table 2 (20.0% /
  26.7%); confirms the ch5 mechanistic story carries forward.

Why the interaction framing. The cell-level Cliff's δ pattern,
the matched-pair Δ pattern, and the engagement-class Δ pattern
all converge on the same conclusion: the trace's effect
direction depends on selection strategy. Three independent cuts
of the data agreeing is stronger evidence than a single test;
the framing should reflect that.

Spine impact. The spine's defended claim #2 ("selection and
structural enrichment produce the most substantial and
interpretable differences") is unchanged; ch6 was always the
empirical carrier for the structure half. The realignment
sharpens what ch6 contributes — not just that structure
matters, but that it matters conditionally on selection.

Consequences for the validation batch. §8.2 framing updated to
test both interaction directions in parallel: does L2 sustain
its single-shot advantage on stratified across five trajectory
steps, and does L2 sustain its single-shot underperformance or
parity on wpb. Trajectory mechanics, acceptance rule, and
per-step rebuild rules unchanged.

Alternatives considered.

- **Reporting only the cell-level Δ_step distribution** (the
  original primary). Rejected: the modal-proposal repetition
  surfaced by Analysis D — six top hashes appear in both L1 and
  L2 cells of the same strategy — means the cell-mean view
  mixes trace-changed-something coordinates with no-effect
  coordinates and obscures the actual mechanism. The §11.2
  matched-pair view restricted to the different-hash subset
  (§11.2 + Analysis F) is the precise correction.
- **Promoting trace-engagement classification to primary headline**
  rather than primary auxiliary. Rejected: small Absent class
  sizes (n ≈ 4–5) and the regex-based classification rule make
  this a heuristic measurement; primary headlines should be on
  more robust statistics.
- **Re-running the primary batch under tighter hypothesis
  framing.** Rejected: the data already tells the interaction
  story cleanly across three independent cuts; new data isn't
  needed to update the framing. The validation batch (§8.2,
  unchanged in mechanics) tests whether the interaction
  survives compounding.

Reference. Verification commit 8b225c4
(`_verification_analysis.md` / `_verification_analysis.json`,
five analyses A–E); the Analysis F different-hash matched-pair
extension committed alongside this entry; the new §1, §11, §14,
§8.2 of `chapter6_design.md`; the prior 2026-04-25 N=60 rule
lock entry; the 2026-04-24 primary-claim revision entry — now
superseded for the sub-claim about argmax-equivalence reduction
being the primary mechanism, but unsuperseded for the
structure-vs-divergence-trace decision.

---

**2026-04-29 — Chapter 6 verification probes ran on Vertex AI (recorded retroactively in 2026-05-12 ch6 transport backfill).**

Decision. The chapter-6 verification probes that exercised the
Vertex AI provider for chapter-6-sized L2 prompts ran on Gemini
2.5 Pro served via Vertex AI rather than the direct Gemini API.
The model and core parameters (`gemini-2.5-pro`,
`temperature=1.0`, `max_output_tokens` per the probe-config
table below, `reasoning_effort="medium"` mapped to a Vertex
`thinkingBudget` per
`thesis/code/chapter5/llm_client.py::_vertex_thinking_budget`)
were the same as the ch5 / ch6 production specification on the
model and parameter axes; the transport axis is what this entry
records.

Two probe artifacts evidence the routing:

- `thesis/artifacts/chapter6_vertex_dsq_probe.json` — `ran_at`
  2026-04-29T19:13:11Z, 5 probe calls under five Vertex configs
  (`baseline`/`tokens_12k`/`tokens_8k` at the `global` location,
  `region_uc1`/`combined` at `us-central1`), `reasoning_effort`
  `"medium"`, `inter_probe_sleep_s=30.0`, project
  `ahd-project-494817`, all errors recorded as Vertex 429
  RESOURCE_EXHAUSTED responses. `tokens_8k` (global,
  `max_output=8192`) and `combined` (us-central1,
  `max_output=12288`) returned `status="ok"`; the other three
  returned 429.
- `thesis/artifacts/chapter6_vertex_dsq_probe2.json` — `ran_at`
  2026-04-29T19:15:46Z, 2 follow-up calls at us-central1
  (`uc1_16k` at `max_out=16384` / `think=12288`; `uc1_20k` at
  `max_out=20480` / `think=16384`), both 429 — establishing the
  upper bound of what the Vertex DSQ allocation on this project
  would survive at the time.

Both probe artifacts name "Vertex API" explicitly in their
recorded error strings; the routing is unambiguous.

Reason. The verification probes used the same Vertex fallback
the chapter-7 calibration probe later used (same provider, same
mapping function). The 2026-05-05 chapter-7 calibration-probe
artifact's `provider_fallback` block names the chapter-6
verification probes as precedent for the fallback ("Chapter 6
verification probes used the same fallback for the same
reason"); this entry records what that precedent was, on its own
date, rather than only by reference from a later chapter's
artifact.

Retroactive note. This entry is recorded retroactively as part
of the 2026-05-12 chapter-6 transport backfill. The 2026-05-05
chapter-7 transport-authorization entry (commit `f5f623`)
introduced the discipline of recording chapter-level transport
choices as standalone decisions-log events, and explicitly
flagged the chapter-6 asymmetry in its "Note on chapter 6"
section. The chapter-6 verification-probe runs themselves
predate the discipline; this entry brings them into compliance
retroactively, on the same pattern as the chapter-6 master-seed
retroactive backfill (commit `1defbc3`). **No decision is being
made now**; the verification probes ran on Vertex at the time
they ran, and this entry records that empirical fact in the
log. The retroactive parenthetical in the title preserves
findability under the file's newest-at-top convention while
keeping the entry's body date (2026-04-29) faithful to when the
underlying probe runs occurred.

Date recovered from the `ran_at` field of both probe artifacts
(`chapter6_vertex_dsq_probe.json`, `chapter6_vertex_dsq_probe2.json`)
plus a corroborating `[vertex] setting GOOGLE_CLOUD_LOCATION=us-central1`
log line and `started: 2026-04-30T15:05:19` / `finished:
2026-04-30T21:20:11` timestamp pair in
`thesis/artifacts/chapter6_resume_run.log`, both consistent with
the late-April-2026 Vertex-fallback timeline.

Scope clarification. The entry's nominal scope is the
chapter-6 verification probes specifically. While preparing the
entry, the investigation recovered explicit transport metadata
for the chapter-6 primary and validation batches as well; that
finding is reported here transparently for findability,
without expanding this entry's decision scope:

- Chapter-6 primary batch (per-call `provider` field across the
  240 records under `thesis/results/chapter6_primary_batch_gemini/`):
  93 records carry `provider="gemini"` (timestamps span
  2026-04-25T08:34:54Z through 2026-04-27T19:46:09Z) and 147
  records carry `provider="vertex"` (timestamps span
  2026-04-29T19:41:34Z through 2026-04-30T21:15:52Z, picking up
  about 30 minutes after the verification probes finished). The
  primary batch is therefore mixed-transport, with the gemini
  records preceding the verification probes and the vertex
  records following them; the resume run that completed the
  primary batch was the cutover event, executed via
  `thesis/code/experiments/chapter6_smart_resume.py`
  (`MAX_OUTPUT_TOKENS_BY_PROVIDER["vertex"] = 12288`,
  `VERTEX_LOCATION = "us-central1"`).
- Chapter-6 validation batch (60 step-records under
  `thesis/results/chapter6_validation_batch_gemini/`): no
  top-level `provider` field, but every record's
  `llm_metadata.raw_response_metadata` carries `vertex_location:
  "us-central1"` and `vertex_project: "ahd-project-494817"`.
  All 60 records ran via Vertex (timestamps span
  2026-05-01T01:02:06Z through 2026-05-01T04:15:07Z).

Whether the primary-batch mixed-transport split materially
affects any chapter-6 finding is a separate analytical question
this entry does not resolve; surfacing the split here makes
that question askable rather than hidden behind a missing log
event. A future entry, if needed, could record the
primary-batch and validation-batch transports as standalone
chapter-level events on their own dates, on the same retroactive
pattern.

Reference.
- `thesis/artifacts/chapter6_vertex_dsq_probe.json` —
  verification probe v1 (5 calls, 2026-04-29T19:13:11Z).
- `thesis/artifacts/chapter6_vertex_dsq_probe2.json` —
  verification probe v2 (2 calls, 2026-04-29T19:15:46Z).
- `thesis/code/experiments/chapter6_vertex_probe.py` and
  `thesis/code/experiments/chapter6_vertex_dsq_probe.py` (and
  `chapter6_vertex_dsq_probe2.py`, `chapter6_vertex_dsq_probe3.py`)
  — the probe scripts; the `vertex_probe.py` docstring
  explicitly states "before pointing the chapter-6 resume run at
  it", confirming the probes' role as transport verification for
  the subsequent ch6 resume run.
- `thesis/code/chapter5/llm_client.py::_vertex_thinking_budget`
  — the mapping function the ch7 transport-authorization entry
  also referenced (`low → 1024`, `medium → 10240`, `high →
  24576`).
- `thesis/code/experiments/chapter6_smart_resume.py` lines
  102–110 — the resume driver that consumed the verification
  probes' findings (Vertex `max_output_tokens=12288`, location
  `us-central1`).
- `thesis/artifacts/chapter6_resume_run.log` — the resume run
  log carrying the `[vertex] setting
  GOOGLE_CLOUD_LOCATION=us-central1` line and the
  2026-04-30T15:05:19Z–2026-04-30T21:20:11Z runtime window.
- `thesis/artifacts/chapter7_calibration_probe.json` —
  `provider_fallback` block, the prompting reference that named
  the chapter-6 verification probes as precedent.
- Decisions log 2026-05-05 "Chapter 7 transport authorized:
  Vertex AI for primary batch and forward..." — the discipline
  precedent and the entry whose "Note on chapter 6" section this
  backfill closes.
- Decisions log 2026-04-24 "Chapter 6 master seed and namespace
  (recorded retroactively in 2026-05-05 ch7 backfill)" (commit
  `1defbc3`) — the retroactive-discipline format precedent.

---

**2026-04-25 — Chapter 6 Level-2 trace rendering rule revised a second time: N=60 rows (head=12, stride=48), calibrated against an empirically-measured ~1.04 chars/token ratio. Supersedes the same-day N=200 and N=150 locks, both of which were token-budget-infeasible.**

Decision. Part (a) of the chapter 6 Level-2 rendering rule
(`compact4` numeric format) is unchanged. Part (b) (row
selection) changes from N=150 (head=30 + stride=120) to
**N=60 (head=12 + stride=48)**. Algorithm, applied verbatim
to the extracted `list[DecisionRecord]` of length `n`:

```
if n <= 60:
    selected_positions = [0, 1, ..., n-1]    # all rows kept
else:
    head      = [0, 1, ..., 11]              # first 12 rows verbatim
    tail      = numpy.linspace(12, n-1, 48, dtype=int).tolist()
    selected  = sorted(set(head) | set(tail))
```

Same shape of rule as the prior N=200 and N=150 locks; only
the row count and head size shrink further. The defensive
`n <= 60` branch is not expected to fire on the committed
pool (every trace is exactly 5000 rows). Both parts apply at
every Level-2 call in chapter 6 — primary batch, validation
trajectories, any retroactive re-runs. Any change is a
decisions-log event that re-invalidates ch6 Level-2 results.

Why this rule, in three steps.

1. **The two prior 2026-04-25 locks (N=200, N=150) both missed
   Gemini's 1,048,576-token input limit.** The N=200 lock
   assumed a ~4 chars/token ratio typical of natural-language
   prompts; the smoke batch (commit `505c70e`) measured a
   1,051,400+-token L2 prompt against the limit and the API
   returned HTTP 400. The N=150 lock used the v2 probe's
   ~2.06 chars/token estimate (`chapter6_render_rule_probe_v2.json`,
   commit `265c39d`), which itself was derived from the failed
   N=200 prompt's lower bound (the API's 400 message reports
   only the limit, not the actual count, so 2.06 was an
   overestimate of chars/token). The re-run smoke at commit
   `d96c680` measured a 1,623,318-char N=150 L2 prompt that
   also exceeded the 1,048,576-token limit — confirming the
   true chars/token ratio is below ~1.55.

2. **Phase A of this task calibrated the actual chars/token
   ratio at `r = 1.0361` by sending an N=50 L2 prompt and
   reading `prompt_tokens` from a successful Gemini 2.5 Pro
   response.** The calibration script
   (`thesis/code/chapter6/experiments/calibrate_chars_per_token.py`,
   committed in this commit) renders the same
   `(stratified_representative, level=2, set_index=0)` prompt
   the smoke driver does, but with the production renderer's
   row-selection function locally overridden to N=50 (head=10
   + stride=40) so the prompt is small enough to fit inside
   the input limit and produce a successful round-trip with
   usage metadata.

   Calibration result:
   - prompt char count: 545,328
   - prompt_tokens (from API): 526,335
   - empirical r = 545,328 / 526,335 = **1.0361 chars/token**
   - sanitize_status: ok (proposal returned cleanly)

   The dense-numeric trace body tokenizes at almost exactly
   one character per token. This is much denser than any
   natural-language content (which typically runs 3–5 cpt)
   and was the load-bearing assumption error in the two
   prior locks.

3. **N_max derived from `r` and a 25 %-headroom budget,
   producing the locked N=60.** Using the v1 probe's
   `compact4_full` mean of 16,345,219 chars across 5000 rows
   (mean 3,269 chars/row), and reserving 20 K tokens for the
   Level-1 block plus 262 K tokens (25 % of the limit) as
   headroom buffer, the available budget for trace body is
   1,048,576 − 20,000 − 262,000 = 766,576 tokens. With
   per-row token cost = 3,269 / 1.0361 = 3,155 tokens, and
   k = 4 counterexamples,

       N_max = 766,576 / (4 × 3,155) ≈ 60.74 rows

   Rounded down to the nearest 10: **N_max = 60**. (The N=50
   calibration prompt's empirical per-row cost was somewhat
   lower than the formula's 3,269 chars/row average — head-
   sampled rows are early-instance and have shorter
   open_bins lists than the full-trace average — so the
   actual headroom at N=60 is closer to ~40 % of budget
   rather than the formula's 25 %. The formula's
   conservative bias is intentional given the two prior
   wrong-side-of-the-limit estimates.)

Honest note on the chapter's claim. At N=60 the rendered
trace shows the LLM 60 / 5000 = **1.2 %** of the incumbent's
actual decisions on each instance. The chapter's claim
("structural enrichment helps") is still meaningfully tested
— the LLM still sees per-decision structural detail
(item-by-item open_bins capacities, scoring margins, chosen
slots) that it had no access to at Level 1 — but the row
sample is roughly a third of the original N=200 design's
intended evidence density. §14 names this honestly as a
property of the rendering rule, not a flaw. A future thesis
that aims at higher row counts would need either a higher-
context model than Gemini 2.5 Pro, a tighter numeric format
than `compact4`, or a structural compression of `open_bins`
itself — all three of which were considered and rejected for
this chapter (see below).

Measured distortion at N=60. From the v1 probe (re-run for
this task with a new `compact4_60` cell, this commit):

- `margin_zero_rate`: rendered mean **0.288** vs true full-
  trace mean 0.327, delta **−3.9 pp**. Comparable to the
  N=150 (−4.7 pp) and N=200 (−3.7 pp) locks; the
  margin-zero distortion is essentially flat across N.
- `new_bin_rate`: rendered mean **0.473** vs true full-trace
  mean 0.409, delta **+6.4 pp**. Larger than at N=150
  (+4.0 pp) and N=200 (+2.6 pp); the head-heavy sampling's
  over-representation of new-bin events grows as N shrinks.
  Still single-digit pp; named as a limitation in §14.

Alternatives considered and rejected.

- **Tighter numeric format** (e.g. `compact3`: `f"{x:.3g}"`).
  Rejected. The probe's `compact4` floats average ~5 chars
  each; `compact3` would average ~4 chars. That's a ~20 %
  size reduction — would let us use ~N=72 instead of N=60.
  But `compact3` would render `0.997` (a near-tie margin)
  as `0.997` (no change since 3 sig fig is already exact) —
  no, wait: `0.997` is already 3 sig fig. The actual loss
  is at the boundary: a margin of `0.0123` would render as
  `0.012` (compact3) vs `0.01233` (compact4 with 4 sig
  fig). For chapter 6's claim, scoring margins below 0.01
  are common (~33 % of decisions have `margin == 0`), and
  margins in the 0.01-0.10 range are exactly the ones the
  LLM should be able to read as "near tie." Losing the
  fourth sig fig would narrow that range. The marginal
  budget gain isn't worth it.
- **Stripping `open_bins` to summary statistics.** Rejected,
  same reason as both prior locks: the heuristic's scoring
  function acts on specific bin-capacity vectors.
- **Dropping to a higher-context model.** Rejected, would
  change the spine's locked primary-model commitment (#4).
- **N below 50.** Rejected — the row sample would be too
  thin to test the structure claim. (The task's surface-and-
  stop floor was 50; N=60 sits one bucket above it.)

Spine impact. None. Defended claim #2 is unchanged; the
primary-model commitment (#4) is unchanged. This is a
re-operationalization of one rendering choice, calibrated
empirically rather than estimated.

Reference.
- `thesis/code/chapter6/experiments/calibrate_chars_per_token.py`
  (this commit) — the calibration script that produced
  `r = 1.0361`.
- `thesis/artifacts/chapter6_render_rule_probe.json` (this
  commit) — re-run with the new `compact4_60` and
  `lossless_60` cells; the prior 10 cells preserved
  byte-identically. Source of the N=60 distortion numbers.
- `thesis/artifacts/chapter6_render_rule_probe_v2.json`
  (commit `265c39d`) — the bin-truncation alternative
  measurements (still rejected for this lock; same reason
  as both prior locks).
- `thesis/artifacts/chapter6_trace_stats.json` (commit
  `ec23424`) — full-trace baseline for the distortion
  comparison (`margin_zero_rate` mean 0.327, `new_bin_rate`
  mean 0.409).
- Smoke-batch failures: commits `505c70e` (N=200 over) and
  `d96c680` (N=150 over).
- `thesis/writing/chapter6_design.md` §7.4 (rule spec
  amended), §7.5 (framing paragraph amended), §14
  (distortion bullet amended).
- Decisions-log 2026-04-25 N=200 lock and N=150 lock —
  superseded by this entry; remain as-is per the log's
  append-only discipline.

---

**2026-04-25 — Chapter 6 Level-2 trace rendering rule revised: N=150 rows (head=30 + stride=120), full open_bins preserved. The 2026-04-25 N=200 lock was infeasible at Gemini 2.5 Pro's 1,048,576-token input limit (smoke batch 505c70e measured ~1.07 M tokens worst case).**

Decision. Part (a) of the chapter 6 Level-2 rendering rule
(`compact4` numeric format) is unchanged. Part (b) (row
selection) changes from N=200 (head=40 + stride=160) to **N=150
(head=30 + stride=120)**. Algorithm, applied verbatim to the
extracted `list[DecisionRecord]` of length `n`:

```
if n <= 150:
    selected_positions = [0, 1, ..., n-1]    # all rows kept
else:
    head      = [0, 1, ..., 29]              # first 30 rows verbatim
    tail      = numpy.linspace(30, n-1, 120, dtype=int).tolist()
    selected  = sorted(set(head) | set(tail))
```

Same shape of rule as the prior N=200 lock; only the row count
and head size shrink. The defensive `n <= 150` branch is not
expected to fire on the committed pool (every trace is exactly
5000 rows). Both parts apply at every Level-2 call in chapter 6
— primary batch, validation trajectories, any retroactive
re-runs. Any change is a decisions-log event that re-invalidates
ch6 Level-2 results, on the same discipline as ch5's prompt-
template commitments.

Why this rule. The prior 2026-04-25 N=200 lock was infeasible
in production. The smoke batch (commit `505c70e`) ran one
Level-2 call and got HTTP 400 from the Gemini 2.5 Pro endpoint
with the message *"The input token count exceeds the maximum
number of tokens allowed 1048576."* Direct measurement of the
rendered Level-2 prompt: 2,166,388 chars (2.07 MB) which
tokenized to ~1,051,400 tokens at the dense-numeric ~2.06
chars/token ratio actually observed for this prompt. The §7.4
lock's "comfortably inside Gemini 2.5 Pro's practical input
budget" claim assumed a higher chars-per-token ratio (closer to
4, typical of natural language); the trace's tokenization is
~half that.

A third probe (`chapter6_render_rule_probe_v2.json`, commit
`265c39d`) was run to re-measure the candidate rules at the
empirical 2.06 chars/token ratio and to evaluate two new
bin-truncation alternatives:

- **`compact4_200_full_open_bins`** (the previous lock): max
  k=4 = 1,069,767 tokens. Headroom = **−21,191** tokens.
  Confirms the smoke result; over the limit by ~2 %.
- **`compact4_150_full_open_bins`** (this entry's choice): max
  k=4 = 800,365 tokens. Headroom = **+248,211** tokens (24 %
  of limit). Fits with comfortable margin.
- **`compact4_200_open_bins_50`** (cap each row's open_bins at
  50): max k=4 = 108,672 tokens. Massive headroom but distorts
  the bin-capacity distribution (mean IQR preservation 0.94).
- **`compact4_200_open_bins_20`** (cap at 20): max k=4 = 79,682
  tokens. Even more headroom but distorts more (mean IQR
  preservation 0.76).

The rendering rule revisited the previous N-vs-bin-truncation
trade-off with the new token-budget reality. The choice
between "shrink N" and "truncate open_bins" is the same
trade-off the prior 2026-04-25 lock entry rejected
bin-truncation for: *"the heuristic's scoring function acts on
specific bin-capacity vectors, and removing those vectors
removes the LLM's ability to check its reasoning against
concrete cases."* That principle still applies. Trading row
count for bin fidelity is the right direction; the only
question was whether N=150 keeps the rendered trace stable
enough across instances.

The v1 probe (re-run for this task with a new `compact4_150`
cell, commit hash on this commit) measured the N=150
distortion against the full-trace baseline:

- `margin_zero_rate`: rendered mean **0.2796** vs true full-
  trace mean 0.3268, delta **−4.73 pp**.
- `new_bin_rate`: rendered mean **0.4493** vs true full-trace
  mean 0.4089, delta **+4.04 pp**.

For comparison: at N=200 the deltas were −3.70 pp / +2.61 pp;
at N=100 they were −4.75 pp / +5.41 pp. N=150 sits
approximately halfway between N=200 and N=100 on
`margin_zero_rate` (closer to N=100) and likewise on
`new_bin_rate` (also closer to N=100 but not as far as
N=100's +5.41 pp). All single-digit percentage points; same
qualitative direction (head-heavy sampling under-represents
margin-zero events and over-represents new-bin events). N=150
is a more conservative interpolation between the budget-
infeasible N=200 and the per-instance-unstable N=100.

Why N=150 over N=100. The v1 probe (original 8-cell version,
commit `3a19c0a`) measured N=100's per-instance
`new_bin_rate` range at 0.23 (vs the full-trace per-instance
range of 0.01) — more than 20× the full-trace spread. The
N=100 sample is small enough that instance-to-instance
variance in early-decision packing dynamics surfaces strongly
in the rendered trace, making counterexamples within the same
prompt visibly inconsistent in their open-bin dynamics in ways
the full trace is not. The 2026-04-25 N=200 lock's
alternatives-considered-and-rejected entry rejected N=100 on
exactly this ground. N=150 is closer to N=200 in stability
and closer to N=100 in distortion; the v1 probe's
`new_bin_rate` per-instance range at N=150 is ~0.06 (read
from the new cell's stats), about a quarter of N=100's
spread. Acceptable.

Alternatives considered and rejected.

- **`compact4_200_full_open_bins`** (no change). Rejected:
  empirically infeasible, see above.
- **`compact4_200_open_bins_50`** and
  **`compact4_200_open_bins_20`**. Rejected: bin-capacity
  truncation removes specific bin-capacity vectors from the
  prompt that the heuristic's scoring function operates on.
  At 50 bins the IQR distortion is mild (mean preservation
  0.94); at 20 it is significant (0.76). The chapter's
  primary claim depends on the LLM proposing scoring-function
  edits the prompt's evidence supports — narrowing the
  evidence to a 20- or 50-bin sample of an ~830-bin
  distribution constrains what the LLM can reason about in
  ways shrinking N does not.
- **`compact4_100`**. Rejected per the per-instance-variance
  argument above (still applicable).
- **Scoping out of Gemini 2.5 Pro to a higher-context model.**
  Rejected: would change the spine's locked primary-model
  commitment (#4) and is out of scope for a rendering-rule
  revision. The Gemini 2.5 Pro 1 M-token limit is the
  reality the rule must fit inside.

Consequences for chapter 6 claims. Findings remain conditional
on the rendering rule (§14's "trace-size reduction rule is an
empirical choice" bullet stands). The §14
"Rendering-rule distortions" bullet is amended in this commit
with the new N=150 numbers. The "uniform-stride sampling is
one rule among many" bullet is unchanged.

Consequences for prior commits. The smoke batch (commit
`505c70e`) demonstrated the previous rule's infeasibility.
Only one Level-1 record was written under the prior lock; no
Level-2 batch was run (the very first Level-2 call failed with
HTTP 400). No data invalidation is needed — only the rule, the
renderer, and the §14 distortion bullet update. The prior
2026-04-25 rule-lock entry remains as-is per the log's
append-only discipline; it correctly records what was decided
at the time and what evidence supported it then.

Spine impact. None. Defended claim #2 is unchanged; the
primary-model commitment (#4) is unchanged. This is a
re-operationalization of one rendering choice forced by the
empirical token-limit reality.

Reference.
- `thesis/artifacts/chapter6_render_rule_probe_v2.json`
  (commit `265c39d`) — token-count headroom for the four
  candidate rules at the empirical 2.06 chars/token ratio.
- `thesis/artifacts/chapter6_render_rule_probe.json` (this
  commit) — re-run with the new `compact4_150` and
  `lossless_150` cells; the prior 8 cells preserved
  byte-identically. Source of the N=150 distortion numbers
  cited above.
- `thesis/artifacts/chapter6_trace_stats.json` (commit
  `ec23424`) — full-trace baseline (`margin_zero_rate` mean
  0.327, `new_bin_rate` mean 0.409), unchanged.
- Smoke-batch commit `505c70e` — the empirical proof that
  the prior N=200 rule was infeasible.
- `thesis/writing/chapter6_design.md` §7.4 (rule spec
  amended in this commit), §7.5 (framing paragraph amended),
  §14 (distortion bullet amended).
- Decisions-log 2026-04-25 "Chapter 6 Level-2 trace
  rendering rule locked: `compact4` numeric format, 200 rows
  per counterexample, first-20%-head + uniform-stride tail"
  — the prior lock; supersedes its rule but not its
  rationale (the bin-truncation rejection still applies).

---

**2026-04-25 — Chapter 6 Level-2 trace rendering rule locked: `compact4` numeric format, 200 rows per counterexample, first-20%-head + uniform-stride tail.**

Decision. The chapter 6 Level-2 prompt renders each
counterexample's incumbent decision trace under the following
two-part rule, applied identically at every Level-2 call in
the primary and validation batches:

(a) **Numeric format = `compact4`.** Floats render via Python
    `f"{x:.4g}"` (4 significant figures); integers render via
    `str(x)`; the boolean `new_bin` renders as the lowercase
    tokens `true` / `false`. The rule applies uniformly to
    every numeric field in the row schema (§7.2): `item`,
    every element of `open_bins`, `score_winner`,
    `score_runner_up`, `margin`, `cap_after`.

(b) **Row selection = 200 rows per counterexample, first-40
    head + 160-row uniform-stride tail.** Given the extracted
    `list[DecisionRecord]` of length 5000:

      head = the first 40 rows (positional indices 0..39,
             corresponding to arrival indices 1..40)
      tail = the rows at positions selected by
             numpy.linspace(40, len(trace)-1, 160, dtype=int)
             (which always includes both endpoints — position
             40 and position 4999, i.e. arrival indices 41
             and 5000)
      selected = sorted(set(head positions) | set(tail positions))

    `set` union deduplicates any collision between head and
    tail; in practice for `(5000-row trace, 200-row cap)` the
    union has exactly 200 distinct positions and no dedup
    fires. If a trace has fewer than 200 rows, the rule is
    total: every row is kept. The committed pool's traces are
    all exactly 5000 rows so the defensive branch is not
    expected to fire.

The rule is chapter-6-wide and chapter-6-only; it is not
applied retroactively to chapter 5 (which has no trace block).

Why this rule. Two probe artifacts measured the cost and the
distortion of every cell in a 2 × 4 (numeric_format ×
row_count) candidate matrix against the committed
counterexample pool:

- `thesis/artifacts/chapter6_trace_stats.json` (commit
  `ec23424`) — per-instance trace shape (every trace is
  exactly 5000 rows, full-trace lossless render is 26.9 M
  chars mean / 27.7 M worst-case per instance, true
  full-trace `margin_zero_rate` = 0.327, true full-trace
  `new_bin_rate` = 0.409).
- `thesis/artifacts/chapter6_render_rule_probe.json` (commit
  `3a19c0a`) — the 2 × 4 cell aggregates with k=4 prompt-
  size projections and distortion deltas vs the lossless-full
  baseline.

Key numbers driving the choice:

- **Tractability.** The full-trace cells (`compact4_full`,
  `lossless_full`) project to ~65 MB and ~109 MB respectively
  for a worst-case k=4 prompt; both far exceed any practical
  Gemini 2.5 Pro input budget. Subsampling is doing the
  heavy lifting on tractability, not the format choice alone.
- **Format savings.** `compact4` saves ~39 % characters vs
  `lossless` uniformly across all four row-count cells, with
  no information loss the LLM can plausibly act on (17-sig-fig
  floats are not actionable structural signal).
- **Budget headroom at the chosen cell.** `compact4_200`
  projects to ~2.13 MB k=4 mean and ~2.17 MB k=4 worst-case
  for the trace portion alone. The Level-1 block (incumbent
  code, reference code, k=4 instance summaries, framing) sits
  on top. ~2.17 MB leaves comfortable room inside Gemini 2.5
  Pro's ~4 MB practical input budget at the locked
  `max_output_tokens=32768` setting.
- **Distortion at the chosen cell.** The N=200 head+stride
  subsample shifts the rendered `margin_zero_rate` from 0.327
  (full) to 0.290 (a −3.7 percentage-point delta) and the
  rendered `new_bin_rate` from 0.409 (full) to 0.435 (a +2.6
  percentage-point delta). These are small distortions,
  consistent across the 30 pool instances, and are made
  explicit as limitations in `chapter6_design.md` §14.
- **Subsample stability.** At N=200, per-instance
  `new_bin_rate` ranges 0.38–0.50 (range 0.12); at N=100 the
  same per-instance range explodes to 0.35–0.58 (range 0.23,
  vs the full-trace range of 0.01). N=200 is the smallest
  row-count cell in the matrix that keeps per-instance
  rendered statistics roughly comparable across the pool.

Alternatives considered and rejected.

- `compact4_full` (every row, compact4 format). Rejected —
  intractable: ~65 MB k=4 worst-case, far beyond any
  available LLM context.
- `lossless_*` at any row count. Rejected — strictly
  dominated by the corresponding `compact4_*` cell on cost
  with no actionable information preserved by 17-sig-fig
  floats. The 39 % savings from `compact4` are pure
  tractability win.
- `compact4_400` (400 rows, compact4). Rejected — the
  ~4.39 MB k=4 worst-case sits at the edge of the practical
  input budget once the Level-1 block is layered on top, and
  the marginal distortion improvement vs N=200 is small
  (`margin_zero_rate` delta of −3.91 pp at N=400 vs −3.70 pp
  at N=200; `new_bin_rate` delta of +2.48 pp at N=400 vs
  +2.61 pp at N=200). The extra rows do not buy proportional
  fidelity.
- `compact4_100` (100 rows, compact4). Rejected — within
  budget (~1.08 MB k=4 worst-case) but per-instance
  variance in `new_bin_rate` jumps to range 0.23 from the
  full-trace range of 0.01, more than 20× the full-trace
  spread. The N=100 sample is small enough that
  instance-to-instance variance in early-decision packing
  dynamics surfaces strongly, making the rendered trace
  inconsistent across counterexamples in ways the full
  trace is not.
- Stratified sampling (e.g. balanced by margin-zero rows or
  by new-bin decisions) or importance sampling (e.g.
  oversample non-zero-margin rows). Rejected — both would
  correct the measured `margin_zero_rate` and
  `new_bin_rate` distortions, but at the cost of imposing a
  hypothesis about which decisions matter, which is exactly
  the pre-filter the chapter's full-trace design chose to
  avoid (decisions-log 2026-04-24 "Chapter 6 primary claim
  revised...", which made the unfiltered baseline the
  empirical input for chapter 6's primary claim). Named in
  `chapter6_design.md` §14 as future work, not rejected on
  merits — deferred.
- `open_bins` summarization (e.g. report only the chosen
  bin's neighbours, or report a histogram of capacities
  instead of the vector). Rejected — the heuristic's
  scoring function acts on specific bin-capacity vectors,
  and removing those vectors removes the LLM's ability to
  check its proposed scoring change against concrete cases.
  Subsampling preserves the vector-level structure at each
  shown decision; collapsing the vector itself does not.

Consequences for chapter 6 claims. Any chapter 6 finding is
conditional on this rendering rule. The two
distortion-magnitude bullets in `chapter6_design.md` §14
name the specific deltas above. A future extension could
vary the rendering rule as an axis of its own; that is
future work, not part of this chapter.

Consequences for implementation. `chapter6_design.md` §18
step 3 (Level-2 prompt renderer + template file) can now
proceed. The template file
`thesis/code/chapter6/prompt_template_level2.txt` will
encode this rule in code; `chapter6_design.md` §7.4 / §7.5 /
§9.2 (rewritten in this same task's commit) encode it in
prose. Any future change to either side is a decisions-log
event that re-invalidates ch6 Level-2 results.

Spine impact. None. Defended claim #2 is unchanged; this is
an operationalization choice for an experiment carrying that
claim.

Reference.
- `thesis/artifacts/chapter6_trace_stats.json` (commit
  `ec23424`) — first probe; full-trace baseline measurements.
- `thesis/artifacts/chapter6_render_rule_probe.json` (commit
  `3a19c0a`) — second probe; 2 × 4 candidate-rule
  measurements.
- `thesis/writing/chapter6_design.md` §7.4 (locked rule
  spec), §7.5 (locked prompt format and framing text), §9.2
  (Level-2 template now fully specified), §14 (two new
  rendering-distortion limitation bullets), §18 step 3
  (template file creation, now unblocked).
- Decisions-log 2026-04-24 "Chapter 6 primary claim revised
  from argmax-equivalence-rate reduction to
  structural-enrichment-improves-proposal-quality" — the
  source of the unfiltered-baseline commitment that this
  rule operationalizes.
- Decisions-log 2026-04-24 "Chapter 6 implements two
  structural levels (raw, raw + trace); diagnosis deferred
  to chapter 8 future work" (Entry B) — the source of the
  Level-2 scope this rule renders.

---

**2026-04-24 — Chapter 6 primary claim revised from argmax-equivalence-rate reduction to structural-enrichment-improves-proposal-quality; argmax-equivalence rate demoted to secondary continuity metric.**

Decision. Chapter 6's primary claim is rewritten from the
earlier "trace enrichment reduces argmax-equivalence rate"
framing to a broader "structural enrichment of counterexamples
produces measurably better LLM-proposed improvements" claim,
operationalized through the same Δ_step distribution and
compound-improvement trajectory metrics chapter 5 used. The
chapter's Level 2 is correspondingly redefined as the
incumbent's complete per-decision packing trace on the
counterexample instance (every arrival index, no filter, no
reference-side rows), not the divergence-filtered parallel
trace of the prior framing. Argmax-equivalence rate continues
to be reported in chapter 6 as a 2×2 table for continuity
with chapter 5 §5.5.3, but as a secondary metric — a Level-2
cell that fails to reduce argmax-equivalence rate while
shifting Δ_step distribution favorably is now a chapter-
positive outcome, not a falsifying one.

Prior state. The earlier 2026-04-24 entry titled "Chapter 6
implements two structural levels (raw, raw + trace);
diagnosis deferred to chapter 8 future work" — referred to
below as Entry B — recorded the sharpened primary claim as
"reduces argmax-equivalence rate, inheriting from chapter 5
§5.5.3," in the context of the rationale for dropping
Level 3. Per the log's append-only discipline that entry is
not amended; it remains the historical record of the
Level-3-deferral conversation. The present entry supersedes
its primary-claim sentence only.

Reason. The argmax-equivalence-rate framing was too narrow.
It tied chapter 6's primary outcome to a specific chapter 5
mechanistic finding (the ~23% silent-edit rate at chapter 5's
structural floor), turning the chapter into a test of "does
trace enrichment fix this one ch5 mechanism?" rather than a
test of the structural-enrichment axis the spine commits to.
The thesis spine's defended claim #2 is the broader
commitment: the biggest and most interpretable differences in
refinement behavior come from counterexample selection and
structural enrichment, not from prompt phrasing or the
particular reference heuristic. Chapter 5 carried the
selection half; chapter 6 must carry the structural half. The
revised claim does that — it asks whether richer structural
information about the incumbent's behavior on the
counterexample instance produces better proposals, measured
on the same primary metrics ch5 used, so that any
Level-2-vs-Level-1 effect can be read directly against ch5's
distributions.

A second concern with the prior framing: it presupposed that
the right Level-2 trace is divergence-filtered (only the
arrival indices where the incumbent and reference chose
different bins). That choice bakes in a specific hypothesis
about which decisions matter — namely, those where ch5's
argmax-equivalence is most likely to be flipped. The revised
trace contains every decision the incumbent makes; it adds
information without that pre-filter. If the divergence-
filtered subset turns out to carry the signal, that is a
legitimate follow-up question, but it is one chapter 6 can
ask only if it first measures the unfiltered baseline.

Consequence for the trace extractor. The committed
divergence-based `thesis/code/chapter6/trace_extractor.py`
(commit 785e047, with 12 passing unit tests) was written for
the prior framing. It is not the right artifact for the
revised chapter. Adapting it to incumbent-side full-trace
semantics — keeping the harness-alignment mechanics, the
`_replay` logic, the `to_dict` serialization, and the
abstract-candidate-set scoring; dropping the parallel
reference replay and the divergence filter — is now §18
step 1 of the revised implementation order in
`chapter6_design.md`. The existing extractor and its tests
are not deleted in this task; the adaptation lands in the
next implementation task.

Consequence for the metrics hierarchy. `chapter6_design.md`
§11 now reports Δ_step distribution per cell (§11.1) and
compound-improvement trajectory metrics per cell (§11.2) as
co-primary, with Δ_gate / generalization gap (§11.3) and
argmax-equivalence rate (§11.4) as secondary, per-instance
win rate (§11.5) as tertiary, and the reasoning-code
consistency check (§11.6) as auxiliary. The 2×2 headline
figure in §12 is now a Δ_step / compound-improvement cell
caption rather than the prior `eq_rate, Δ` caption.

Alternatives considered and rejected.
- Retain argmax-equivalence rate as the primary claim and
  run the divergence-based trace as Level 2. Rejected: this
  collapses chapter 6 onto a test of one ch5 mechanism
  rather than testing the spine's structural-enrichment
  axis, and pre-filters Level 2 on a hypothesis about
  which decisions matter.
- Run both divergence-based and incumbent-side traces as
  separate Level-2 variants (a 2×2×2 grid). Rejected: this
  would make the chapter's claim about a specific
  sub-structure ("incumbent vs divergence vs ...") rather
  than about structural enrichment in general; it also
  doubles the LLM-call budget without informing the
  primary structural-enrichment question, and the prior
  framing's divergence variant is preserved as a named
  design variation in `chapter6_design.md` §14
  ("incumbent-only trace") for later study.

Spine impact. None. Defended claim #2 is unchanged; this
revision aligns chapter 6's empirical operationalization
with that claim's broader framing rather than the prior
narrower argmax-equivalence-rate operationalization. No
spine edit is required.

Reference.
- `thesis/writing/chapter6_design.md` §1 (revised claim),
  §6.2 (Level 2 redefinition), §7 (incumbent-side trace
  spec), §11 (reordered metrics), §14 (incumbent-only as
  named limitation), §18 step 1 (extractor adaptation).
- `thesis/docs/00_thesis_spine.md`, "Three claims to
  defend" — claim #2.
- Decisions-log 2026-04-24 entries (all unchanged by this
  revision):
    - "Chapter 6 runs on `h_eoh` only; the 'both
      incumbents' outline clause is retired" (Entry A).
    - "Chapter 6 implements two structural levels (raw,
      raw + trace); diagnosis deferred to chapter 8 future
      work" (Entry B, the entry whose primary-claim
      sentence is superseded).
    - "Spine commitment #2 unlocked and narrowed to
      `h_eoh`-only empirical scope".
- Commit `30d6e84` (chapter6_design.md rewrite).
- Commit `785e047` (the divergence-based trace extractor
  whose adaptation is now §18 step 1).

---

**2026-04-24 — Spine commitment #2 unlocked and narrowed to `h_eoh`-only empirical scope.**

Decision. `00_thesis_spine.md`'s Locked architectural
commitment #2 is rewritten from its original "Two canonical
incumbents / all experiments in chapters 5, 6, 7 run from one
of these two starting points / two-regime structure is the
organizing axis" form to a narrower commitment: `h_eoh` is the
sole empirical incumbent for chapters 5, 6, and 7; `h_strong`
is retained as a defined-but-unrealized concept (the intended
output of one standardized repair pass on `h_eoh`, which did
not produce a viable fine-tuning-regime incumbent — chapter 1
§1.4); and the two-regime structure is retained as a conceptual
frame in chapter 3 rather than as an empirical axis.

Preamble discipline. The spine's preamble states that the four
locked architectural commitments "cannot be revisited without
an explicit conversation in which they are unlocked." This
entry is that conversation's record. The unlocking is scoped
to commitment #2 only; commitments #1 (post-hoc on EoH), #3
(single testbed), and #4 (single primary model) are unaffected.
The three defended claims are unchanged; the "What this thesis
does not claim" list is unchanged. Any future revision of
commitment #2 is governed by the same unlocking rule.

Reason. The spine as it stood contained a pre-existing internal
contradiction:

- Commitment #2 stated that "all experiments in chapters 5, 6,
  7 run from one of these two starting points [`h_eoh` or
  `h_strong`]" and that "the two-regime structure is the
  organizing axis of the empirical chapters."
- The same file's "What this thesis does not claim" list stated
  that the two-regime structure has *not* been empirically
  validated, that the fine-tuning regime relies on an `h_strong`
  the standardized repair pass failed to produce, and that the
  thesis therefore operates in the large-headroom regime only.

The contradiction was introduced by the `h_strong` negative
result (chapter 1 §1.4) without a corresponding spine edit; the
empirical record was updated, the non-claims list was updated,
but commitment #2 was left in its pre-negative-result form. The
present entry brings commitment #2 into line with the empirical
record rather than the other way around.

Downstream consistency. The narrowing is already reflected
everywhere in the planning documents except commitment #2
itself:

- Chapter 5 is `h_eoh`-only per decisions-log 2026-04-20
  "Chapter 5 operates on `h_eoh` only; regime comparison is
  chapter 7."
- Chapter 6 is `h_eoh`-only per decisions-log 2026-04-24
  "Chapter 6 runs on `h_eoh` only; the 'both incumbents'
  outline clause is retired" (Entry A of the 2026-04-24 pair).
- Chapter 7's outline paragraph already states "Runs on `h_eoh`
  only, following the scope narrowing recorded for Chapter 5";
  the planned repair-history sub-experiment has been demoted
  to a discussion-level item.
- The glossary still defines `h_strong` as "the output of one
  standardized, deterministic, fully-specified repair pass
  applied to `h_eoh`… defined in chapter 4." That definition
  remains correct as an intended concept and needs no edit;
  chapter 4 will narrate the failed repair pass when drafted.

Alternatives considered and rejected.
- Leave the contradiction in place and resolve it only in
  chapter 8 prose. Rejected: every future reader of the spine
  (reviewer, examiner, or later self) sees the contradiction
  until then, and the spine is meant to be the one document
  that cannot quietly drift.
- Attempt a second `h_strong` repair pass with a different
  rule set so commitment #2 holds as originally written.
  Rejected: this was already considered and rejected in the
  2026-04-24 Entry A rationale — a re-specified repair pass
  would itself be a new thesis axis (repair-pass design) and
  falls outside the current scope.

Spine reference. This entry updates commitment #2 directly.
The three other locked commitments are unaffected; the
preamble, the three defended claims, and the "What this thesis
does not claim" list are unchanged.

Reference.
- `thesis/docs/00_thesis_spine.md` — commitment #2 (edited),
  preamble (unchanged), "What this thesis does not claim"
  list (unchanged).
- `thesis/writing/chapter1_draft.md` §1.4 (h_strong negative
  result).
- Decisions-log 2026-04-20 "Chapter 5 operates on `h_eoh`
  only" and 2026-04-24 Entry A "Chapter 6 runs on `h_eoh`
  only".
- `thesis/docs/03_thesis_outline.md` — chapter 5, 6, 7
  paragraphs (all already `h_eoh`-only).

---

**2026-04-24 — Chapter 6 runs on `h_eoh` only; the "both incumbents" outline clause is retired.**

Decision. Chapter 6 operates on `h_eoh` only. The clause in
`03_thesis_outline.md`'s Chapter 6 paragraph that previously
read "Runs on both incumbents" is retired, and the paragraph is
rewritten in the same task that lands this entry.

Reason. The outline clause was written against the spine's
originally-planned two-regime structure (large-headroom `h_eoh`
plus fine-tuning `h_strong`). The `h_strong` repair pass failed
to produce a viable fine-tuning-regime incumbent — documented
in Chapter 1 §1.4 and elevated to the spine's "What this thesis
does not claim" list, which now states explicitly that the
thesis operates in the large-headroom regime only and defers
the regime-contrast discussion to Chapter 8. Chapter 5 already
narrowed to `h_eoh` on the same basis (decisions-log entry
2026-04-20, "Chapter 5 operates on `h_eoh` only"); Chapter 6 is
now made consistent with that precedent. The spine's three-axis
commitment (selection, structure, cardinality) is unchanged —
chapter 6 still carries the structural-enrichment axis; only
the planned regime multiplication is removed.

Alternatives considered and rejected.
- Attempt a second `h_strong` repair pass with a different rule
  set to recover a fine-tuning incumbent for chapter 6.
  Rejected: a re-specified repair pass would itself be a new
  thesis axis (repair-pass design) and falls outside chapter 6's
  structural-enrichment scope.
- Leave the "runs on both incumbents" clause in the outline and
  simply not run `h_strong` experiments. Rejected: creates a
  documented inconsistency between the outline's planned scope
  and the chapter's empirical record, which is precisely the
  drift the planning docs are meant to prevent.

Reference.
- `thesis/writing/chapter6_design.md` §2 (non-goal: incumbent
  regime), §17 item 1.
- `thesis/writing/chapter1_draft.md` §1.4 (h_strong negative
  result).
- `thesis/docs/00_thesis_spine.md`, "What this thesis does not
  claim" list.
- Decisions-log 2026-04-20, "Chapter 5 operates on `h_eoh` only;
  regime comparison is chapter 7" (the precedent being extended
  to chapter 6; chapter 7's regime sub-experiment was itself
  already demoted to discussion-level — see
  `03_thesis_outline.md` Chapter 7).

---

**2026-04-24 — Chapter 6 implements two structural levels (raw, raw + trace); diagnosis deferred to chapter 8 future work.**

Decision. Chapter 6 implements Level 1 (raw counterexample,
chapter 5's rendering) and Level 2 (raw + per-decision
divergent-decisions trace). Level 3 (raw + trace + diagnosis),
which appears in the glossary's Structural-enrichment ladder,
is not studied empirically in this thesis. Diagnosis remains a
glossary-defined concept and is relocated to Chapter 8 as a
named future-work direction.

Reason. Two distinct problems with running Level 3 inside
chapter 6:

(i) A Level-3-vs-Level-2 comparison would confound the
    chapter's core question ("does more structure help?") with
    a taxonomy-validity question ("is our diagnostic taxonomy
    the right one?"). Neither question is cleanly answerable
    while the two are entangled, and the structural-enrichment
    axis is the one chapter 6 is built to measure.
(ii) A rule-based failure taxonomy presupposes the failure→fix
    mapping that the LLM is meant to discover. Producing
    diagnosis labels at this stage of the thesis means *we*
    write down "instance X fails because of Y; try patch family
    Z," then measure whether the LLM benefits from reading our
    labels — which is circular with respect to the thesis's
    generative claim that an LLM can extract improvement
    direction from counterexample structure.

Sharpened primary claim for chapter 6. With Level 3 out,
chapter 6's primary claim is framed around the
argmax-equivalence rate inherited from Chapter 5 §5.5.3:
augmenting each counterexample with a per-decision trace of
divergent packing decisions reduces the rate at which
LLM-proposed edits preserve the incumbent's argmax on every
scored packing decision. This is a more mechanistic and more
directly-measurable claim than a generic "more structure is
better" one, and it is falsifiable inside the 2×2 primary
table (see `chapter6_design.md` §11.1, §12).

Alternatives considered and rejected.
- Run diagnosis with an ad-hoc minimal taxonomy drawn from
  chapter 5's argmax-equivalent-reasoning bundle (the 15
  annotated traces in `07_reasoning_notes.md`). Rejected for
  the circularity reason above: even a minimal taxonomy drawn
  from our own data still presupposes the failure→fix mapping
  and contaminates the chapter's measurement of whether
  structural information alone carries improvement signal.
- Retain Level 3 in the chapter and relabel it as a robustness
  check rather than a core comparison. Rejected: this dilutes
  the chapter's sharpened mechanistic claim, adds proposal-
  budget cost for additional cells without corresponding thesis
  return, and leaves diagnosis's taxonomy-validity problem
  unresolved rather than cleanly deferred.

Reference.
- `thesis/writing/chapter6_design.md` §2 (non-goal: diagnosis),
  §6 (levels), §11.1 (primary metric), §14 (limitations),
  §17 item 2.
- `thesis/writing/chapter5.md` §5.5.3 (argmax-equivalence
  finding).
- `thesis/docs/05_glossary.md`, "Structural enrichment"
  ladder and "Diagnosis" entry (updated in the same task to
  mark Diagnosis as glossary-defined but not empirically
  studied in this thesis).

---

**2026-04-24 — Chapter 6 master seed and namespace (recorded retroactively in 2026-05-05 ch7 backfill): `MASTER_SEED_CH6 = 20_260_424`, namespace prefix `ch6:`.**

Decision. Chapter 6 uses an independent master seed
`MASTER_SEED_CH6 = 20_260_424` with namespace prefix `ch6:` for
all sampling reproducibility. The seed-derivation functions are
the chapter 5 functions with the `ch5:` namespace prefix replaced
by `ch6:`. Every chapter 6 proposal record logs the master seed,
the strategy name, the structural level, the set index, the seed
index, and both derived seeds. The cell name is
`(strategy, level)` (e.g., `stratified_representative@L2`).
Reproducibility = master seed + protocol + committed prompt-
template files. Verbatim from `chapter6_design.md` §13.

Reason. Disjoint per-chapter seed namespaces keep each chapter's
sampling reproducibility independent of the others. Chapter 5
established the convention with `MASTER_SEED_CH5` and the `ch5:`
namespace prefix; chapter 6 inherits the convention with its own
master seed and prefix; chapter 7 continues the same pattern (see
the 2026-05-05 entry locking `MASTER_SEED_CH7 = 20_260_505`,
namespace prefix `ch7:`).

Retroactive note. This entry is recorded retroactively as part of
the 2026-05-05 ch7 backfill. The chapter 7 design-doc landing
(commit `c8bbb6b`) introduced the discipline of recording the
chapter's master seed as a standalone decisions-log entry; the
chapter 6 design-doc landing (commit `932f9a8`, dated 2026-04-24)
locked `MASTER_SEED_CH6 = 20_260_424` inside `chapter6_design.md`
§13 but did not file a parallel decisions-log entry, creating an
asymmetry between the two chapters' findability discipline. This
entry closes that asymmetry by recording what was already locked
in chapter 6's design doc on 2026-04-24. **No decision is being
made now**; the master seed itself was locked at the time of the
chapter 6 design-doc landing. The retroactive parenthetical in
the title preserves findability under the file's newest-at-top
convention while keeping the entry's body date (2026-04-24)
faithful to when the underlying lock occurred.

Reference.
- `thesis/writing/chapter6_design.md` §13 — the original lock,
  unchanged since the chapter 6 design-doc landing
  (commit `932f9a8`).
- Decisions log 2026-05-05 "Chapter 7 master seed and namespace
  locked: `MASTER_SEED_CH7 = 20_260_505`, namespace prefix
  `ch7:`" — the entry that introduced the standalone-entry
  discipline and triggered this backfill.

---

**2026-04-23 — Validation protocol: acceptance requires argmax-distinctness from current incumbent (revision to §6.2).**

Decision. The chapter-5 validation trajectory (§6.2 step 5)
acceptance rule is revised from the original strict
`Δ_step_local > 0` to:

    accepted iff Δ_step_local >= 0
      AND the proposal is argmax-distinct from the current
          incumbent on train_step
          (i.e., per-instance bin counts differ on ≥1 instance).

Four explicit acceptance_reason labels are recorded per step:

    - accepted_improvement           Δ_step_local > 0 (argmax
                                     distinct is implied).
    - accepted_behavioral_change     Δ_step_local = 0 and argmax-
                                     distinct (new acceptance case).
    - rejected_regression            Δ_step_local < 0.
    - rejected_argmax_equivalent     Δ_step_local = 0 and argmax-
                                     equivalent (no behaviour
                                     change at all).

The rule is implemented in
`thesis/code/chapter5/validation.py::should_accept_proposal`;
the trajectory driver, the unit tests, and any future protocol
revision all funnel through that one function.

Reason. The 2026-04-23 findings-log entry
"Chapter 5 primary batch: 23% of proposals land in h_eoh's
argmax-equivalence class without being byte-identical copies"
established that ~23% of primary-batch proposals produce bit-
identical bin counts to the incumbent despite syntactic edits.
Under the original strict `>0` rule these proposals would be
rejected anyway (Δ_step_local = 0), but for the *wrong* reason:
they appear to be numerical ties rather than what they actually
are — behaviourally identical heuristics. And crucially, the
strict rule *also* rejects a legitimate acceptance case:
Δ_step_local = 0 with argmax-distinct bin counts (i.e., the
proposal moved the incumbent to a *different plateau of equal
quality*). The revised rule distinguishes the two cases with
explicit labels and accepts the second, which lets trajectories
explore the neighbourhood of behaviourally-equivalent-quality
heuristics rather than freezing at `h_eoh` when every
Δ_step_local = 0 is treated identically.

Implications for chapter-5 findings.
- Per-step acceptance_reason is reported alongside the numerical
  metrics. The count of ``accepted_behavioral_change`` decisions
  is itself an observation about how often each selection
  strategy produces non-trivial argmax-flipping proposals.
- Trajectory dynamics change. Under the original rule the
  trajectory could freeze at h_eoh after step 1 if the LLM
  happened to produce an argmax-distinct but numerically-tied
  proposal. Under the revised rule the trajectory continues
  exploring behaviourally different incumbents even when the
  objective is flat.
- No change to §9 metrics. Δ_step_local and Δ_step_cumulative
  are defined the same way; only the promotion rule moves.

Spine impact: none. The three-axis chapter-5 design is
unchanged; this is a methodological refinement.

Alternatives considered and rejected.
- Keep the strict `>0` rule. Rejected: the 23% argmax-equivalence
  rate means most trajectory steps would reject, wasting the
  experiment's measurement capacity, and the rejection would be
  attributed to "numerical tie" when in fact the real reason is
  a distinction between behavioural change (worth accepting) and
  behavioural equivalence (not worth accepting).
- Accept on `Δ_step_local >= 0` without the argmax-distinct
  requirement. Rejected: this would count argmax-equivalent
  proposals as trajectory advances, which is semantically wrong
  — the incumbent didn't actually change, so the step was a
  no-op dressed up as progress.
- Raise the acceptance threshold to `Δ_step_local > 1` (or
  similar). Rejected: thresholding on a noisy integer mean
  across 30 instances introduces a hyperparameter with no
  principled choice; the argmax-distinctness test has the
  principled "behaviour must actually change" interpretation.

Reference.
- 2026-04-23 findings log, "Chapter 5 primary batch: 23% of
  proposals land in h_eoh's argmax-equivalence class..."
- `thesis/code/chapter5/validation.py`
- `thesis/code/chapter5/tests/test_validation.py` (5 acceptance
  tests + pool-rebuild byte-equivalence test)

---

**2026-04-23 — Chapter 5 primary batch: Gemini 2.5 Pro at reasoning_effort=medium, max_output_tokens=32768, most_discriminative dropped due to pool collision.**

Decision. Chapter 5's primary batch runs on Gemini 2.5 Pro with
`reasoning_effort="medium"`, `max_output_tokens=32768`,
`temperature=1.0`, and 3-second inter-call sleep. Five selection
strategies participate — worst_only, worst_plus_best,
uniform_random, random_discriminative, stratified_representative —
each producing 60 proposals per the §5.7 determinism table, for
300 primary LLM calls. The validation batch (top-3 × 3
trajectories × 5 steps = 45 calls) uses the same settings. These
are **driver-level** settings; the production defaults in
`llm_client.py` stay at low / 8192 so ad-hoc callers are unaffected.

Reason. The 2026-04-23 Gemini-medium-32k probe (see
`thesis/results/chapter5_refcode_probe_gemini_medium_32k_2026_04_23/`)
returned Category A on every criterion: 6/6 sanitize-ok at the
`step_by_step_reasoning_then_code` format, cross-strategy Δ_step
spread of 520 bins ([−516.67, +3.53]), 2/6 strategies beating
h_eoh (random_discriminative at +3.53 with win 0.70;
stratified_representative at +2.97 with win 0.53), 4/6 at or
near parity, engagement rates 0.83 on both instance-detail and
reference-heuristic mentions. Mean cost $0.0713 per call; mean
latency 116.5 s. Extrapolation to the 300-call primary
batch: ~$21 and ~10 h sequentially — well inside budget.

Why medium over low. Low-reasoning on earlier probes produced
less elaborate proposals and did not show the Chapter 5 signal
at the same strength. Medium-reasoning probe data is the
strongest signal we have; running a dedicated low-comparison
probe before the batch would delay it by another task-cycle for
marginal information.

Why max_output_tokens=32768. Medium reasoning on Gemini's
OpenAI-compatible shim consumed 5500–8000 reasoning tokens per
call in the probe. 32768 gives ~3–6× headroom and stays well
within Gemini 2.5 Pro's 65K output limit. The prior 8192
ceiling truncated 100% of calls during hidden reasoning (see
`thesis/results/chapter5_refcode_probe_gemini_medium_2026_04_23/`).

Why most_discriminative is dropped. Glossary: returns the k
counterexamples with largest `|gap|`. On the committed pool
(`h_eoh_counterexample_pool.json`) the top-4 `|gap|` values are
all negative: |−25|, |−21|, |−20|, |−15|; the largest positive
gap is +14. So most_discriminative returns the same
CounterexampleSet as worst_only on this pool, and running both
would produce statistically equivalent distributions modulo LLM
stochasticity — 60 duplicated calls at ≈$4.20. This is a
property of *this* pool, not of the strategy definition; a pool
where positive and negative extremes coexist at similar
magnitude would keep the strategies distinct. The collision
was already noted in the 2026-04-20 findings-log entry. The
experimental matrix marks CH5-04 as *dropped* with a pointer
here.

Batch scope. Primary: 5 × 60 = **300 calls**, ≈$21, ≈10 h.
Validation: 3 × 3 × 5 = **45 calls**, ≈$3, ≈1.5 h. Total:
**345 calls**, ≈$24, ≈11.5 h sequential.

Alternatives considered and rejected.
- Run all six strategies including most_discriminative. Rejected
  per pool collision above.
- Rebuild the pool with different composition to keep
  most_discriminative distinct from worst_only. Rejected: the
  pool was built by the canonical pool-builder from
  `train_select`; rebuilding would invalidate downstream scoring
  already cached in `score_cache.json` and change the
  counterexample semantics mid-chapter.
- Run Gemini at `reasoning_effort="low"` on the same prompt.
  Rejected for reasons above.
- Run on Groq Llama at the enriched prompt. Rejected: the free
  tier's daily-token-cap constraints make a 345-call batch take
  ~13 days to complete in isolated windows.

Open items.
- worst_only showed catastrophic outlier (Δ_step = −516) at n=1
  in the probe. If the 60-proposal distribution reproduces that
  pattern, Chapter 5's reporting of outlier-sensitive metrics
  (means) must be complemented by robust alternatives (medians,
  trimmed means). §9/§10 already anticipate this.
- Validation top-3 selection: likely random_discriminative,
  stratified_representative, and worst_plus_best based on probe
  n=1, but final selection waits on the primary batch.
- The 2-hour smoke run confirmed plumbing (3/3 sanitize-ok at
  production settings) but returned three Δ_step = +0.00
  proposals, which is within n=1 stochasticity but worth
  flagging if the primary batch's Δ_step distribution is
  unexpectedly zero-concentrated.

---

**2026-04-23 — Chapter 5 prompt: render full counterexample tuple (reference code included) and adopt STEP_BY_STEP_REASONING + CODE output format.**

Decision. Chapter 5's mutation prompt now renders the reference
heuristic's full source code in a new `=== REFERENCE HEURISTIC ===`
section, and requires the LLM to produce two labelled sections in
response: `STEP_BY_STEP_REASONING` (a four-point numbered reasoning
trace, under 400 words) followed by `CODE` (the complete new
`score` function). Exact section wording is locked verbatim in
`thesis/code/chapter5/prompt_template.txt` and mirrored in
`chapter5_design.md` §7. The sanitizer is upgraded to a two-stage
pipeline: stage 1 (`extract_code`) recognizes
`step_by_step_reasoning_then_code`, `analysis_then_code`,
`code_only`, or `malformed` formats and pulls out the code slice
plus any reasoning text; stage 2 runs the existing parse /
signature / runtime checks. New failure label
`failed_extraction` fires only on `malformed`. Reasoning text is
preserved in each proposal's provenance record but is not scored.

Reframing of reference-code inclusion. The glossary defines a
counterexample as the tuple
`(instance, candidate, reference, gap, trace_slice?, diagnosis?)`.
Previously Chapter 5's prompt rendered the `reference` element as
bin counts only — an under-rendering of the tuple, not a deliberate
information floor. The updated prompt renders the full
tuple's *static* content (instance summary, reference source,
gap). `trace_slice` (chapter 6) and `diagnosis` (chapter 7) remain
out of scope for chapter 5. The reference's identity and the
reason it was chosen are still withheld from the prompt text —
only its role is described.

Reason. Empirical, from author-run exploratory probes on 2026-04-22
and 2026-04-23:

- Level-3 instance summary alone (no reference code): reasoning
  present but proposals still mostly catastrophic.
- Adding reference source helped partially; mixed win/loss
  counterexample composition helped more; adding the
  STEP_BY_STEP_REASONING + CODE format helped most.
- On Gemini 2.5 Pro, a 14-prompt mixed batch at the full
  (ref-code + reasoning format) regime: 14/14 sanitized, 10/14
  non-negative Δ_step on `train_step`, median Δ_step +0.37, mean
  Δ_step −3.09. A code-only baseline on the same prompts had
  mean Δ_step −20.50.

Chapter 6 separability. Chapter 6's structural-enrichment axis is
per-decision trace slices, orthogonal to static heuristic source.
Including the reference's source in chapter 5 does not encroach on
chapter 6; the axes remain distinct.

Probe strategy. All confirming evidence is on Gemini 2.5 Pro. A
6-call Groq Llama 3.3 70B probe runs before any batch, to check
that Llama can reason at this prompt grain. If it cannot, the
batch decision is revisited.

Alternatives considered and rejected.
- Keep chapter 5's prompt without reference code. Rejected: the
  exploratory evidence is that reference code is part of what
  makes the prompt learnable at this floor.
- Make ref-code inclusion its own chapter 5 axis (with / without).
  Rejected: doubles the batch, no budget.
- Adopt the shorter `ANALYSIS + CODE` format. Rejected:
  `STEP_BY_STEP_REASONING` performed better in probes and gives
  the post-hoc analysis more structure to work with. The
  shorter format is retained as a legacy fallback in the
  sanitizer only.
- Include a "reference origin" explanation (e.g. "alternative
  heuristic from the same search process"). Rejected: adds
  provenance that is not a property of the tuple itself.

Open items.
- The 400-word reasoning cap is enforced as instruction only, not
  by the sanitizer. May revisit if the LLM consistently exceeds.
- Provenance records now include reasoning text, which grows
  per-proposal JSON size. Manageable but noted.

---

**2026-04-23 — Chapter 5 prompt raised from bare instance ID to instance-summary (Level 3).**

Decision. Chapter 5's mutation prompt no longer shows a thin
`(instance_id, incumbent_bins, reference_bins, diff)` table. Each
counterexample is now rendered as a **Level-3 instance summary**:
`n_items`, `capacity`, `incumbent_bins`, `reference_bins`, `diff`
(= ref − cand = +gap); an `item_distribution` block with mean, std,
min, max, quartiles 25/50/75, percentiles p10/p90, and a 10-bucket
histogram of width `capacity / 10`; and an `item_samples` block with
largest 5 descending, smallest 5 ascending, near-median 5, and a
`sha256(instance_id)`-seeded random 5. Instance IDs remain anonymized
as `instance_01…`. The reference heuristic's source code is **not**
included; the reference exists only as an anonymous bin-count
opponent. Diff sign convention is unchanged (= +gap; see 2026-04-21
diff-sign fix). Lives in `thesis/code/chapter5/instance_summary.py`
and `prompt_template.txt`; consumed by `prompt_builder.py`.

Reason. Two 2026-04-23 off-spec probes showed the bare-ID regime
produced catastrophic proposals across every selection strategy
(Δ_step on the order of −230 bins per instance set, with near-total
failure on train_step). The LLM had no evidence against which to
reason about *which* instance to fix, so the selection axis — the
variable chapter 5 is built to measure — could not be distinguished
from noise. Without per-instance evidence the prompt collapses the
six strategies into the same "random rewrite" distribution. A Level-3
summary is the minimal evidence that restores the selection axis
without leaking into chapter 6 (structural trace slices) or chapter 7
(diagnosis). A narrower middle regime (reference heuristic source
code only, no statistics) was considered but produced only partial
recovery in probes and introduces a second-heuristic confound that
would contaminate later chapters.

Alternatives considered.
- Keep the bare-ID floor; treat the catastrophic Δ_step as a chapter
  5 finding in itself. Rejected: with no signal to distinguish
  strategies, the primary comparison is uninformative and the chapter
  has no headline result.
- Include the reference heuristic's source code instead of / in
  addition to the instance summary. Rejected as the standalone floor:
  partial helper in probes, and leaks a second-heuristic identity
  into a chapter that isolates selection strategy.
- Skip straight to Level-5 (trace slices). Rejected: collapses
  chapters 5 and 6 into one, loses the controlled axis story.

---

**2026-04-22 — Provisional chapter 5 batch on Groq + Llama 3.3 70B; Gemini 2.5 Pro remains primary.**

Empirical motivation:

- 2026-04-20: Gemini 3.1 Pro Preview calibration clean (~8.8 s/call at
  locked settings). 2.5 Pro calibration also clean (15.7 s/call).
- 2026-04-21: 3.1 Pro Preview failed (250+ s timeouts). 2.5 Pro
  calibration succeeded, three-call probe clean.
- 2026-04-22: 2.5 Pro pre-batch validation failed on call 1 —
  284 s latency on the same prompt and settings that succeeded at
  15.7 s one day earlier. Proposal quality also regressed: the
  one produced proposal scored Δ_step = −49.57 (losses on 30/30
  train_step instances) vs. the prior Δ_step = −0.77 with
  win_rate 13/30.
- Two days of consecutive Gemini latency/quality failures on
  identical settings and identical prompt have blocked empirical
  progress. The thesis spine already names Llama 3.3 70B on Groq
  as documented backup for reproducibility checks; this decision
  operationalizes that backup for a provisional batch.

Decision: chapter 5's next operational batch runs on
`groq` + `llama-3.3-70b-versatile` as a **provisional** empirical
tool. Results are real and will be analyzed; they are **not** the
thesis's final record.

Primary-model commitment unchanged: Gemini 2.5 Pro remains the
thesis's primary model. When the Gemini API stabilizes, the chapter
5 batch will be re-run on Gemini 2.5 Pro and those results replace
the provisional record.

Disposition of provisional results:
- Stored under `thesis/results/chapter5_provisional_groq/`
  (gitignored, like all `thesis/results/*` directories).
- Analysis scripts and summary JSONs committed as code artifacts.
- Chapter 5 prose IS NOT written against provisional results.
  Prose waits for the Gemini re-run.
- If the Gemini re-run shows qualitatively consistent
  strategy effects, the provisional Groq results may be
  reported as a cross-model robustness check. If the Gemini
  re-run contradicts the provisional results, only the
  Gemini run is reported, and the discrepancy is noted in
  chapter 8 (discussion).

Methodological consequences:
- Llama 3.3 70B is a different model family (open-source,
  non-reasoning) from Gemini 2.5 Pro. Proposal characteristics
  will differ — expect more direct code, less verbose internal
  reasoning, possibly different failure modes at sanitization.
- This is acceptable because the provisional run is not the
  thesis record. It is an operational unblock.
- Settings analogous to Gemini's production settings:

        provider          = "groq"
        model             = "llama-3.3-70b-versatile"
        temperature       = 1.0
        max_output_tokens = 8192 (pending calibration)
        seed              = derived from §11 formulas (Groq accepts seed)
        reasoning_effort  = not applicable (silently dropped)

- Reproducibility note: Groq honors seed, so Groq-provisional
  proposals are byte-reproducible given the same master seed. This
  is **stricter** reproducibility than Gemini 2.5 Pro provides. A
  useful property; does not affect strategy-comparison claims
  within the provisional batch.

Alternatives considered:

(a) Wait indefinitely for Gemini stability. **Rejected** — two days
    of stalling already; unknown recovery timeline.
(b) Switch to Groq as the thesis's new primary model.
    **Rejected** — Llama 3.3 70B is open-source and less-used in
    AHD literature than Gemini; the thesis benefits from primary
    results on a frontier model for external validity.
(c) Commit chapter 5 results from the 2026-04-21 2.5 Pro
    calibration (1 successful proposal) as representative.
    **Rejected** — n=1 is not chapter 5.

Open item: if Gemini instability persists more than ~10 days,
reconsider whether the Groq provisional run should be promoted to
primary for chapter 5 specifically, with the regime-dependence
aspects of the spine renegotiated. This is a thesis-scope
conversation, not an implementation decision.

Implementation: `thesis/code/chapter5/llm_client.py` is now
provider-pluggable with `call_llm(provider=...)`. `call_gemini`
remains as a backward-compat alias. `run_single_proposal(...,
provider="gemini")` defaults to the primary; callers pass
`provider="groq"` for the provisional batch. 87/87 chapter-5
tests green, including 7 Groq-specific hermetic tests.

*Per-provider max_output_tokens sizing.* The Gemini default of
8192 was chosen to accommodate Gemini 2.5 Pro's hidden reasoning
tokens, which empirically consume 5–8× the visible output on the
chapter-5 smoke prompt. Llama 3.3 70B on Groq is non-reasoning:
call 1 of the 2026-04-22 Groq calibration produced its full
proposal in 540 visible completion tokens at temperature=1.0 with
`finish_reason=stop` (no truncation). Groq's free-tier rate limit
is **12,000 TPM** for `llama-3.3-70b-versatile` **and Groq
reserves the full `max_output_tokens` against TPM at request
time**, not against actual usage — using the Gemini default of
8192 exhausts the per-minute budget after 1–2 calls regardless
of the visible output length. `max_output_tokens` defaults are
therefore per-provider:

        MAX_OUTPUT_TOKENS_DEFAULTS = {
            "gemini": 8192,
            "groq":   2048,
        }

with the option to bump Groq's default to 4096 if future
calibration shows truncation on longer proposals. This is NOT a
methodological change — the principle remains "set
`max_output_tokens` large enough that proposals complete
reliably." The value is provider-specific because the billing
model is provider-specific.

**2026-04-21 — Primary LLM swapped from `gemini-3.1-pro-preview` to `gemini-2.5-pro`.**

Empirical motivation:

- Gemini 3.1 Pro Preview showed **28× latency degradation** on
  identical settings between 2026-04-20 and 2026-04-21: the same
  chapter-5 prompt at `reasoning_effort="low"`, `max_output_tokens=8192`
  completed in 8.8 s on 2026-04-20 but timed out at 250+ s on
  2026-04-21. A minimum-overhead liveness probe
  (`"Respond with OK"`, 4 prompt tokens, `reasoning_effort="low"`,
  `max_output_tokens=128`) also degraded — 11.65 s on 2026-04-21 for
  a call that should complete in ≤5 s on a healthy path.
- Google AI Studio tier-1 rate limits differ sharply: **25 RPM for
  `gemini-3.1-pro` vs 150 RPM for `gemini-2.5-pro`**. The 25 RPM
  ceiling would have been the binding constraint for the 405-call
  chapter-5 batch anyway (serial execution at 25 RPM = >16 min
  minimum wall-clock), and tight rate limits on a preview tier are
  also a plausible driver of the observed latency instability
  (backend deprioritization for preview-tier traffic under load).

Decision: chapter 5 (and, implicitly, subsequent LLM-using work)
uses `gemini-2.5-pro` as the primary model.

Why this does NOT violate the spine's "Single primary model fixed"
commitment (2026-04-20 entry):

- The spine commits to holding model choice fixed **across
  experiments**, not to any specific model identity. Model
  selection is a pre-experimental choice.
- **No LLM-scored results have been committed to the thesis.** All
  prior Gemini 3.1 Pro Preview calls were diagnostic (smoke tests
  and calibration probes) and produced only gitignored artifacts in
  `thesis/results/chapter5_smoke/` and
  `thesis/results/chapter5_prebatch_validation/`. No chapter-5
  provenance records, no scoring, nothing empirical made it into
  the thesis record.
- Swapping now means the entire empirical record of the thesis is
  generated on one model. Swapping **after** chapter 5 data was
  collected would have introduced a confound; swapping **before**
  does not.

Methodological consequence:

- Chapter 4's methodology section must describe the model-choice
  decision explicitly, including the rejection of Gemini 3.1 Pro
  Preview due to operational constraints (rate limit + latency
  instability on 2026-04-21), so readers understand why a
  "preview" label does not appear in the model field.
- The `reasoning_effort="low"`, `max_output_tokens=8192`,
  `temperature=1.0` settings (decided 2026-04-21 for 3.1 Pro
  Preview) are **provisionally carried over** to 2.5 Pro pending
  this task's calibration probe. If calibration reveals 2.5 Pro
  behaves meaningfully differently, the settings will be adjusted
  via a follow-up decisions-log entry before the batch launches.

Alternatives considered:

(a) Wait for 3.1 Pro Preview latency to recover and proceed.
    **Rejected** — indefinite timeline; even once latency recovers,
    the 25 RPM rate limit remains binding and preview-tier
    deprioritization could recur.
(b) Swap to Gemini 2.5 Flash for even higher rate limits
    (1000 RPM) and lower cost. **Rejected** — Flash-tier models
    are lower-capacity on code generation; introducing Flash would
    make "proposal quality" a confound with the selection-strategy
    axis chapter 5 is studying.
(c) Request a rate-limit increase or upgrade to a paid tier that
    keeps 3.1 Pro Preview. **Rejected** — cost and timeline
    uncertain; does not address the latency-under-load issue
    observed today.

Spine reference: this entry updates but does not invalidate the
2026-04-20 "Single primary model fixed" decision. The principle
("one model throughout, to avoid confound") stands; the instance
changes from `gemini-3.1-pro-preview` to `gemini-2.5-pro`.

Implementation: `thesis/code/chapter5/llm_client.py::MODEL_ID`
changed; test-suite model-string assertions updated; 79/79 chapter-5
tests still green.

**2026-04-21 — Chapter 5 batch runs at `reasoning_effort="low"` with `max_output_tokens=8192`.**

Empirical motivation from the 2026-04-21 calibration probe (8 real
Gemini 3.1 Pro Preview calls):

- Gemini 3.1 Pro Preview is a reasoning model whose hidden
  chain-of-thought tokens count against `max_output_tokens` and are
  billed at the output rate (~$12/M).
- At default (medium) `reasoning_effort` with `max_output_tokens=4096`,
  the first smoke-test call consumed ~3,930 hidden reasoning tokens
  before producing only 162 visible output tokens before
  `finish_reason: "length"` truncated the proposal mid-function.
  Per-call cost ~$0.051; sanitization failed with `failed_runtime`.
- Raising `max_output_tokens` to 16,384 at medium reasoning made
  truncation **more** likely, not less — the model used the
  additional budget for longer internal reasoning and wrote a
  rambling in-code analysis inside a docstring literal, getting cut
  off mid-string. Sanitization failed with `failed_parse` (syntax
  error, unterminated string literal).
- Switching to `reasoning_effort="low"` at `max_output_tokens=8192`
  reduced reasoning tokens **10.5×** (7,622 → 726 on a comparable
  prompt), cut per-call cost **7×** (~$0.094 → ~$0.013), cut
  latency **8.5×** (74.6s → 8.8s), and produced a substantive
  parseable proposal with clean `finish_reason: "stop"`.

Decision: the chapter 5 primary (360 calls) and validation (45 calls)
batches run at:

    model              = gemini-3.1-pro-preview
    temperature        = 1.0
    max_output_tokens  = 8192
    reasoning_effort   = "low"

Methodological consequence, stated honestly:

- Proposals under `reasoning_effort="low"` are structurally less
  elaborate than under medium or high reasoning. Chapter 5's claim
  is about whether counterexample selection strategies produce
  *distinguishable distributions* of proposals under a fixed
  generation regime; "low reasoning" is part of that fixed regime.
- Because `reasoning_effort` is held constant across all six
  strategies, it is not a confound — it is a shared boundary
  condition. But it **is** a boundary condition: chapter 5's
  strategy-effect findings are conditional on low-reasoning
  generation and should not be claimed to generalize to
  higher-reasoning regimes without further experimentation.
- Chapter 4's methodology section must caveat this explicitly
  when drafted.

Budget implication:

- Expected per-call cost: ~$0.013 (n=1 observation from the
  calibration probe).
- Expected batch cost (405 calls): ~$5.40 point estimate,
  ~$16 ceiling with a 3× variance allowance.
- Substantially below the pre-calibration estimate of $6–$10 that
  assumed default reasoning.

Alternatives considered:

(a) Run medium reasoning at `max_output_tokens=4096`. Rejected —
    calibration showed high truncation rate (1/1 at this setting)
    and per-call cost ~$0.051; batch cost ~$21 plus a very high
    sanitization-failure rate.
(b) Run medium reasoning at `max_output_tokens=16384`. Rejected —
    calibration showed the model expands reasoning to fill the
    budget without improving visible output quality; the one call
    at this setting failed parse inside a string literal.
(c) Use a thinking-budget parameter (Gemini native `thinking_config`
    or `generation_config.thinking_config`, or OpenAI `extra_body`
    wrapper). Rejected — the Gemini OpenAI shim returns HTTP 400
    `INVALID_ARGUMENT "Unknown name ..."` for all three shapes;
    `reasoning_effort` is the only lever available (confirmed via a
    4-call probe on 2026-04-21).
(d) Run half the batch at low reasoning and half at high, comparing.
    Rejected — doubles the LLM budget and dilutes chapter 5's
    single experimental axis (selection strategy). Reasoning-effort
    comparison is a natural chapter 8 follow-up, not a chapter 5
    axis.

Open item: if any strategy's 60-proposal distribution shows a
suspiciously high sanitization-failure rate (>30%) in the primary
batch, `reasoning_effort="low"` may be under-powered for that
strategy, and chapter 5's prose should acknowledge this as a
generation-regime artifact rather than a strategy effect. The
pre-batch validation (6 calls across all six strategies at the
locked settings) is the go/no-go gate before launching the full
batch.

Implementation: `thesis/code/chapter5/llm_client.py` defaults now
match these settings. `thesis/code/chapter5/runner.py` passes them
explicitly at each call site so intent is visible in code review.
Four hermetic tests in `thesis/code/chapter5/tests/test_llm_client.py`
verify (1) `reasoning_effort` appears in the payload when set,
(2) it is omitted when None, (3) it propagates to returned
metadata, and (4) invalid values are rejected with ValueError
before any HTTP request.

**2026-04-21 — Gemini 3.1 Pro Preview OpenAI shim does not accept `seed`; LLM-level stochasticity is temperature-only.**
Empirical observation: the Gemini 3.1 Pro Preview endpoint at
`https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`
returns HTTP 400 `INVALID_ARGUMENT` with message `"Invalid JSON payload
received. Unknown name \"seed\": Cannot find field."` when the request
body includes the OpenAI-standard `seed` field. Confirmed by the
chapter 5 smoke test on 2026-04-21. The OpenAI-compatible shim accepts
most OpenAI chat-completion parameters (`model`, `messages`,
`temperature`, `max_completion_tokens`) but rejects `seed` outright.

Consequence: LLM-level stochasticity for chapter 5 comes entirely from
`temperature > 0`. The per-proposal `llm_seed` values derived from the
sha256-based formulas in `chapter5_design.md` §11 are still produced
and logged into every provenance record; they are used to seed
strategy-side `np.random.default_rng` draws (for stochastic
selection strategies) and to make each call's identity traceable, but
they do NOT influence the LLM's output.

Reproducibility implication: re-running a chapter 5 experiment with
the same `MASTER_SEED_CH5` and the same protocol will produce
byte-identical `CounterexampleSet`s per (strategy, set_index) pair —
selection is fully reproducible. It will NOT produce byte-identical
LLM proposals per (strategy, set_index, seed_index); individual
proposals are stochastic. Reproducibility of chapter 5 is therefore
**distributional, not exact**: statistical summaries across the
60-proposal distributions per strategy (mean, median, IQR, Cliff's
delta between pairs) are expected to be stable under re-run, modulo
sampling variance at n=60.

Alternatives considered:
(a) Switch to the Gemini native (non-OpenAI) API, which may support
    a different determinism mechanism. Rejected — requires rewriting
    `llm_client.py`, and chapter5_design.md §11 already anticipated
    this fallback ("the actual stochasticity comes from
    temperature > 0"). The OpenAI shim is otherwise serving us well.
(b) Drop `temperature` to 0 for deterministic-but-conservative
    generation. Rejected — would eliminate proposal diversity
    exactly when we need it, since chapter 5's claim is about
    whether selection strategies produce distinguishable
    *distributions* of proposals. A single-point-per-seed regime
    defeats the 60-call-per-strategy design.
(c) A companion chapter 4 note warning readers that individual
    proposals are not reproducible and that reporting focuses on
    distributional summaries. **Accepted** as a companion
    disposition, to be addressed when chapter 4 is drafted.

This entry consolidates the §11 fallback path into the canonical
thesis position. `thesis/code/chapter5/llm_client.py` no longer
sends `seed` in the payload; it still accepts the parameter,
records it as `seed_requested`, and authoritatively reports
`seed_honored: false` in every provenance record.

**2026-04-20 — `stratified_representative` strata anchored at zero, not at pool mean.**
The design doc at `thesis/writing/chapter5_design.md` §5.6 defined
the `stratified_representative` strategy's three strata in a way
that is not internally consistent as literally written: the
`strong_wins` and `strong_losses` bounds were described as
`gap ≥ +1σ from mean gap` / `gap ≤ −1σ`, while the `ties_and_small`
clause was written as `|gap| < 1σ`. The two formulations cannot both
hold simultaneously once the pool has a non-zero mean gap. Locked
interpretation:

    strong_wins     := gap ≥ +σ
    strong_losses   := gap ≤ −σ
    ties_and_small  := |gap| < σ

where σ is the population standard deviation of gaps across the
pool, computed once at pool-construction time and fixed thereafter.

Reason: (a) consistent with the thesis's gap sign semantics
(positive gap = candidate wins, negative = reference wins); (b) makes
the `ties_and_small` clause coherent with the other two at the
boundary; (c) decouples strata definitions from whether the pool
happens to skew reference-favoring or candidate-favoring on a given
sample — the strata are relative to zero (no-difference) rather than
to an accidental mean. On the current `h_eoh` pool the mean gap is
−1.9, so mean- vs. zero-anchoring is a meaningfully different
partition; locking zero-anchoring is the right call here.

Alternatives considered: strata anchored at pool mean
(`strong_wins: gap ≥ mean + σ`, `strong_losses: gap ≤ mean − σ`,
`ties_and_small: |gap − mean| < σ`) — rejected, inconsistent with
the `ties_and_small` clause as literally written in the design doc,
and makes the partition depend on an accidental property of the
specific pool rather than on the canonical zero-gap reference.

**2026-04-20 — Chapter 5 operates on `h_eoh` only; regime comparison is chapter 7.**
Chapter 5's selection-strategy experiments run exclusively on the
`h_eoh` incumbent. The regime comparison (whether selection-strategy
effects change between `h_eoh` and `h_strong`) is relocated to
chapter 7, which will re-run a subset of the chapter 5 strategies on
`h_strong` as part of its cardinality and generalization study. This
changes chapter 7's scope: it now carries (cardinality axis) +
(regime-dependence check via h_strong re-runs) + (generalization-gap
study). Reason: isolating selection as the single axis in chapter 5
keeps the statistical power of that chapter on its primary claim,
and the regime contrast is more naturally framed alongside the
cardinality and generalization work of chapter 7. Alternatives
considered: running chapter 5 on both incumbents (rejected — doubles
LLM budget, dilutes selection as the single axis under study);
deferring regime comparison to chapter 8 or future work (rejected —
the two-regime structure from the spine must land somewhere in the
empirical chapters).

**2026-04-20 — Thesis five-subset split defined.**
The canonical thesis split consists of `train_select` (30 × 5k),
`train_step` (30 × 5k), `train_gate` (30 × 5k), `dev` (30 × 5k),
and `test_ood` (30 × 10k). All subsets are generated from a pinned
master seed (`2026_04_20`) plus per-subset offsets, via the
reproducible generator at `thesis/code/weibull_generator.py`. The
three `train_*` subsets are strictly disjoint in both instance IDs
and underlying item sequences; this is the load-bearing discipline
of generalization claim #3 (see `00_thesis_spine.md`). Reason: the
existing bp_online pickles are unseeded and thus unreproducible; a
thesis-level split must be bit-reproducible forever. Thirty instances
per subset was chosen as the smallest size at which mean-bin
differences between similar heuristics rise above single-instance
variance; if chapter-5 experiments reveal this is too small, the
split may be widened — any such widening is a new decision entry.
Alternatives considered: (a) using the existing pickle 5k + EoH
inline 5k as the pool (10 instances total) — rejected, too small
for disjoint three-way splits; (b) reusing `eoh_inline_5k` as one
of the training subsets — rejected, would conflate EoH's training
with the thesis's training and muddy the post-hoc-on-EoH
commitment.

**2026-04-20 — Thesis scoring convention pinned.**
Fixed three interlocking definitional choices before any evaluation
code is written:
(a) Per-instance score is `score(h, I) := -bins_used(h, I)` — raw
    negative bin count, integer, higher is better. No per-instance or
    per-dataset normalization.
(b) Gap is `score(candidate, I) - score(reference, I)` = `bins_used(reference, I) - bins_used(candidate, I)`.
    Positive gap means candidate wins on `I`.
(c) EoH's `objective` field in population JSONs is used only to
    identify `h_eoh` (min-objective member of the final population).
    It is not a thesis score and is never averaged, differenced, or
    fed to chapter 5/6/7 experiments.
Reason: (a) makes dataset-level fitness exactly the mean of per-
instance scores, which is what the counterexample framework requires
and what `Evaluation.evaluateGreedy` already computes (`-mean(bins)`);
it also avoids the dataset-vs-instance L1-normalizer asymmetry found
in EoH's internal fitness. (b) gives positive gaps the intuitive
"candidate wins" reading. (c) quarantines EoH's rounding, its multi-
dataset aggregation bug, and its normalizer choice as properties of
the upstream artifact, not the thesis. Alternatives considered:
(i) match EoH's normalized-excess fitness as the per-instance score —
rejected, the dataset-level L1 normalizer is not a per-instance
quantity and the mean-equals-fitness relationship only holds under a
specific reading; (ii) per-instance normalization by instance-level
L1 bound (what the pre-thesis refinement did) — rejected, mean of
per-instance normalized scores does not equal any natural dataset-
level fitness, introducing a second fitness metric inconsistent with
the harness.

**2026-04-20 — EoH final population pinned to generation 10.**
The canonical "EoH final population" for the thesis is
`examples/bp_online/results/pops/population_generation_10.json`. The
HPC run persisted 11 generations (0 through 10). Generations 8, 9,
and 10 are bit-identical populations; evolution effectively halted
after the gen-7→gen-8 transition. Generation 10 is the chosen name
because it is the last generation persisted, giving the simplest
mapping from "final" to a filesystem artifact. Reason: a byte-
reproducible definition of "the final population" is a prerequisite
for defining `h_eoh` and the reference pool. Alternatives considered:
(a) naming the final population "gen 8" (the first stable generation)
— rejected, less intuitive and inconsistent with EoH's output
directory naming; (b) using a union of gens 7–10 to increase pool
diversity — rejected, breaks the clean "final population"
abstraction.

**2026-04-20 — Reference pool for `h_eoh` defined as the 3 non-incumbent members of the final population.**
For the incumbent `h_eoh` (fitness-best member of the EoH final
population), the reference pool is the 3 other members of the final
population. Their code hashes (sha256, first 12 hex) are
`47d987c33837` (objective 0.01912), `62a2846c597e` (objective
0.01308), and `bea3036f5424` (objective 0.01449). No additional
diversity filter is applied at this pool size. Reason: the glossary
defines the reference pool as "final population minus incumbent,
after diversity filter," and with only 3 candidates any non-trivial
filter is moot. Watch-item: if chapter-5 experiments reveal that the
3-reference pool is too small or too homogeneous to discriminate
between selection strategies, the pool may be widened to include
distinct heuristics from generations 7–9 (adding `23aee4b5f8cf` and
`dc1dbeeeeaa5`, for 5 total). Any such widening is a scope change
and will be logged as its own decision.

**2026-04-20 — Two pre-thesis print-suppression edits grandfathered.**
Two long-standing working-tree modifications were committed to clean
the working tree before thesis work began: one in
`eoh/src/eoh/problems/optimization/bp_online/get_instance.py` and one
in `examples/bp_online/evaluation/get_instance.py`. Each removes a
single `print(opt_num_bins)` debug-trace line; no behavioral change
beyond stdout suppression. The first edit technically violates the
"post-hoc on EoH" commitment because it touches `eoh/`. Reason:
(a) the edits predate the AGENTS.md rule; (b) the change is
behaviorally a no-op; (c) reverting leaves the working tree
persistently dirty with a pre-thesis artifact. If a reviewer ever
requires byte-identity with upstream EoH commit `801c4765...`, a
diff showing the single-line change can be produced on demand.
Alternatives considered: (a) reverting the `eoh/` edit to maintain
upstream byte-identity — rejected, not proportional to the change's
triviality; (b) leaving the working tree dirty indefinitely —
rejected, causes future diff confusion.

**2026-04-20 — Project workspace setup.**
Decided to create a dedicated project workspace for the thesis with six
core navigational documents (00 spine, 01 decisions, 02 state, 03
outline, 04 matrix, 05 glossary), and to organize the work into multiple focused units
inside the project. Reason: a single working
session cannot hold the full thesis in context; explicit
distillation into project knowledge is required to prevent loss across
sessions. Alternatives considered: single mega-conversation (rejected,
context limits), one document per chapter (rejected, no separation
between stable and living state).

**2026-04-20 — Single primary model fixed.**
Decided to fix Gemini 3.1 Pro Preview as the sole primary LLM for the
entire thesis. Reason: prevents model choice from becoming an
uncontrolled confounder across experiments. Llama 3.3 70B on Groq is
retained as a documented backup for occasional reproducibility checks
only. Alternatives considered: comparing models as an additional axis
(rejected, expands the matrix beyond what 30 days supports).

**2026-04-20 — Two canonical incumbents.**
Decided that all empirical chapters operate from one of two fixed
starting points: `h_eoh` (fitness-best of EoH final population) and
`h_strong` (output of one standardized repair pass on `h_eoh`). This
gives the thesis a two-regime structure (large-headroom vs fine-tuning)
that organizes chapters 5, 6, 7. Reason: the historical evidence shows
that counterexample-guided improvement behaves qualitatively differently
when the incumbent is weak versus strong; making this structural rather
than incidental gives the empirical chapters their organizing axis.
Alternatives considered: single incumbent (rejected, loses the regime
contrast); many incumbents from a Pareto front (rejected, expands the
matrix without proportional thesis benefit).

**2026-04-20 — Post-hoc on EoH final population.**
Decided that all thesis contributions sit in a wrapper layer that
operates on EoH's frozen final population. EoH core is never modified.
Reason: gives clean experimental control, matches the comparative-
counterexample theory (the reference is naturally drawn from the
population), and positions the contribution as additive to EoH rather
than competitive. Alternatives considered: interleaved with EoH search
(rejected, couples variables); operating on the full population as a
unit (rejected, muddles the counterexample formalism).

**2026-04-20 — Single testbed: bp_online.**
Decided to scope the thesis to a single problem domain. Multi-problem
generalization is named explicitly as future work. Reason: a second
problem done badly is worse than one problem done rigorously; the
generality claim is relocated from the trace vocabulary to the
architecture. Alternatives considered: bp_online + TSP as a secondary
validation (rejected, insufficient time and dilutes the empirical
focus).

**2026-04-20 — Thesis spine: comparative counterexamples.**
Decided the thesis spine is "counterexamples in statistical-
specification synthesis are discriminative, not absolute; their
selection, structure, and cardinality form a design space." Reason:
this reframing converts the prior "counterexample-guided trace-grounded
repair" framing — which was an architecture description — into a real
research claim that reviewers can disagree with. It also gives the
empirical chapters their three-axis structure. Alternatives considered:
keeping the architecture-description framing (rejected, thesis-light);
direction-vs-magnitude framing (rejected, too narrow to carry the
thesis).
