# Model Router

A small offline CLI tool that recommends which Claude model to use for a
given prompt (and optional reference documents), so you're not manually
guessing between Haiku / Sonnet / Opus / Fable every time you open Claude
Chat.

It never calls the Anthropic API to make the decision — routing is done
entirely with local rules, local embeddings, and (for genuinely ambiguous
cases only) a local offline LLM via Ollama.

**On Fable:** Claude Fable 5 is Anthropic's Mythos-class tier, priced
well above Opus and meant for genuinely extreme, long-horizon work. It's
included here, but deliberately gated behind higher thresholds than
Opus — the goal isn't to avoid its cost, it's to reach for the heaviest
tool only when a task actually needs it, not by default.

## The rules, in plain terms

Before anything gets sent to any AI at all, the router checks your prompt
against a short list of hardcoded, deterministic rules — plain word-counting
and keyword-matching, no AI involved in this step. They're checked in this
order, top to bottom; the first one that matches wins and nothing further
runs. All the thresholds live in `config.yaml`, so they're easy to retune
without touching code.

1. **Fable** if the combined prompt + documents is 4000 words or more
2. **Fable** if 8 or more documents are attached
3. **Fable** if there are 6 or more code blocks
4. **Fable** if the text contains a "fable-signal" word — *days-long,
   multi-day, multi-jurisdiction, regulatory filing, board-ready,
   definitive analysis, cannot afford to be wrong, exhaustive review*
5. **Opus** if the combined prompt + documents is 1500 words or more
6. **Opus** if 4 or more documents are attached
7. **Opus** if there are 3 or more code blocks
8. **Opus** if the text contains a "heavy task" word: *refactor, audit,
   cross-reference, synthesize, reconcile, multi-step, comprehensive,
   end-to-end, architecture*
9. **Haiku** if the prompt is 60 words or fewer, AND there are no
   documents, AND no code, AND none of the words above
10. **Haiku** if it contains a "light task" word — *quick, rename, fix
    typo, format this, one sentence, translate this word* — AND none of
    the heavier words, AND no documents or code, AND it's under 180
    words
11. **Otherwise**, no rule is confident enough to decide — it's handed
    off to the next two layers (semantic, then the offline LLM),
    described below.

## How it decides

```
prompt.txt (+ optional docs/*.txt)
        │
        ▼
 rule layer            → the 11 checks above; obvious cases decided
                          instantly, no AI involved
        │  (no rule fired)
        ▼
 semantic layer         → embeds the prompt locally, compares against
                          example prompts per tier — haiku/sonnet/opus/
                          fable (still no AI generation — just a math
                          similarity score)
        │  (not confident enough on its own)
        ▼
 offline LLM tiebreak   → asks a local Ollama model to make the actual
                          judgment call between all four tiers
        │
        ▼
 recommended model + reasoning, printed and logged
```

A **"Confidence" field only appears when the offline LLM (Ollama) actually
made the call** — it's the LLM's own self-reported confidence in its
answer (0-100%, shown as e.g. `78.00%`), not a technical score from the
matching step. Rule-based and semantic-match decisions don't show a
confidence number at all, since there's no model being asked to judge
anything in those cases — they're just counting and math.

## Effort — a second dimension, separate from tier

Every result shows a **Thinking level** field: `low`, `medium`, `high`, or
`xhigh` (internally this is the "effort" concept — the display label is
just friendlier). This is a real, separate Claude setting (you pick it in
Claude Chat next to the model name, or pass it as the `effort` API
parameter) — the same model can be told to reason more or less before
answering. It exists so a task that's only marginally harder doesn't have
to force a jump to a bigger, more expensive model — it can instead stay
on the lighter model at higher effort.

The terminal output no longer shows a separate "Tier" line — it was
redundant with "Recommended model" (e.g. `claude-sonnet-5` already tells
you it's the sonnet tier), so that slot now shows Thinking level instead.
The underlying tier concept still exists and still drives all the logic
below — it's just not printed as its own line anymore.

How it's decided: when the Ollama tiebreaker actually runs, this is the
LLM's own judgment, exactly like Confidence. Otherwise (rule, semantic,
or tiebreak-fallback decisions) it comes from a feature-based heuristic —
word count, how many numbered/bulleted steps are in the prompt, and
whether a heavy or fable-signal keyword matched — all tunable in the
`effort:` section of `config.yaml`. `xhigh` is capped down to `high` on
tiers that don't support it (`tiers_supporting_xhigh` in config —
currently sonnet, opus, and fable; not haiku).

Worth knowing: thinking level doesn't fix a tier that was wrong to begin
with — it's a separate lever, not a replacement for the tier decision.
For example, a short prompt that happens to contain the word
"architecture" (e.g. "I need an architecture diagram") will still jump
to the Opus tier via the keyword rule, and then get `high` thinking level
on top of that, even though the task itself might genuinely only need
Sonnet. That's a keyword-list precision issue, not something this
resolves — narrowing `heavy_task` keywords in `config.yaml` is the fix
for that specific case,
whenever you want it.


## Setup

**macOS / Linux:**
```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**
Run the same script from Git Bash or WSL (both come with a real `bash` +
`python`):
```bash
bash setup.sh
```
(Native PowerShell/cmd isn't supported directly by `setup.sh` since it's a
bash script — Git Bash, which ships with [Git for Windows](https://git-scm.com/downloads),
is the easiest way to run it unmodified.)

The script will:
1. Create a virtual environment (`.venv`)
2. Install everything in `requirements.txt` (no PyTorch — uses `fastembed`,
   which is CPU-friendly and works fine on a basic laptop)
3. Check for Ollama, and pull the default tiebreak model (`phi4-mini`,
   ~2.5GB) if Ollama is installed
4. Create an empty `routing_log.jsonl`

If Ollama isn't installed yet, get it from https://ollama.com/download —
the router still works without it, it just falls back to a default tier
for ambiguous cases instead of asking the tiebreaker.

## Usage

After setup, activate the environment if it's a new terminal session:
```bash
source .venv/bin/activate        # macOS/Linux/Git Bash
.venv\Scripts\activate           # Windows PowerShell/cmd
```

Then run:
```bash
python main.py
```
It will interactively ask for the path to your prompt file (and, optionally,
a documents file or folder). Or pass them directly:
```bash
python main.py --prompt path/to/prompt.txt --docs path/to/docs_folder
```

Try the bundled example:
```bash
python main.py --prompt examples/sample_prompt.txt --docs examples/docs
```

## Writing prompt/document files

Both the prompt and any "documents" should just be **plain text** (`.txt`)
— write them exactly the way you'd naturally type a message into Claude
Chat: plain sentences, and simple numbered or bulleted lists typed as
`1.`, `2.`, `3.` on their own lines. Nothing fancier needed — you don't
need markdown headers, tables, or any special syntax for the router to
work well.

`.md` files work identically (the router treats `.txt` and `.md` the same
way), so if you *do* want to use markdown formatting like links or tables,
that's fine too — it's optional, not required.

## Tuning it

Everything adjustable lives in `config.yaml` — word-count thresholds,
tier→model mapping, the Ollama model name, keyword lists. No code changes
needed for most retuning.

`router/exemplars.yaml` holds the example prompts the semantic layer
compares against. It ships with a starter set — accuracy improves the most
by adding a handful of your own real prompts here, labeled by which tier
they should route to.

`routing_log.jsonl` accumulates every decision made (timestamp, features,
tier, reasoning) so you can review past calls and adjust thresholds with
real data instead of guessing.

## Rule layer — exact logic

See "The rules, in plain terms" near the top of this file — that section
is the canonical list. Edit thresholds in `config.yaml`.

## Testing the Ollama tiebreaker

Two ways to test the tiebreak step, for different purposes:

**Through the real pipeline** — realistic prompts, each verified to
cleanly bypass every rule above, so they reach the semantic layer for
real. Depending on how confident the semantic layer feels about each
one, some or all may escalate to Ollama — that's expected, not
guaranteed for every single one, since it depends on the actual
embedding comparison, not just word count.

Opus/sonnet boundary (`examples/tiebreak-test-scenarios/`):
```bash
python main.py --prompt examples/tiebreak-test-scenarios/scenario_a_small_change_with_a_catch.txt
python main.py --prompt examples/tiebreak-test-scenarios/scenario_b_client_explanation_with_stakes.txt
python main.py --prompt examples/tiebreak-test-scenarios/scenario_c_migration_planning.txt
```

Fable — one deterministic rule trigger, two opus/fable boundary cases
(`examples/fable-test-scenarios/`):
```bash
python main.py --prompt examples/fable-test-scenarios/fable_scenario_1_keyword_trigger.txt
python main.py --prompt examples/fable-test-scenarios/fable_scenario_2_ambiguous_due_diligence.txt
python main.py --prompt examples/fable-test-scenarios/fable_scenario_3_ambiguous_multi_country_rollout.txt
```
Scenario 1 is designed to hit the hardcoded fable rule directly (you'll
see `Decided by: rule` in the output, every time, no AI involved).
Scenarios 2 and 3 are designed to bypass every rule and land on the
semantic/tiebreak layers instead, so they're the ones that actually
exercise Ollama's judgment between opus and fable.

If a given run doesn't reach Ollama and you want to force more cases into
tiebreak for testing, temporarily raise `confidence_gap_threshold` in
`config.yaml` (e.g. from `0.04` to `0.15`) — a higher threshold means the
semantic layer trusts itself less often, so more cases escalate.

**Directly, bypassing the pipeline** (`test_ollama_tiebreak.py`) — for when
you want a guaranteed, unconditional check of Ollama's judgment on its
own, independent of rules or semantic scoring:
```bash
python test_ollama_tiebreak.py
```
Sends four real-world scenarios (one per tier, including fable) straight
to Ollama. If Ollama isn't running, every scenario will show the
fallback tier instead of a real verdict — that's expected, not a bug.

## Project layout

```
main.py                    CLI entrypoint
config.yaml                 all tunable thresholds/settings
requirements.txt            dependencies (cross-platform, no PyTorch)
setup.sh                    one-shot environment setup
test_ollama_tiebreak.py      standalone test of the Ollama tiebreak step
router/
  parse.py                  reads prompt + document Markdown files
  features.py                word count, code blocks, links, keywords, etc.
  rules.py                   hard-override rule layer
  semantic.py                 local embedding-based scoring
  tiebreak.py                  local Ollama call for ambiguous cases
  effort.py                     effort-level heuristic (2nd output dimension)
  exemplars.yaml               tier-labeled example prompts (4 tiers)
examples/                     a sample prompt + docs to test with
  tiebreak-test-scenarios/      opus/sonnet boundary prompts, for
                                 testing the semantic/tiebreak layers
  fable-test-scenarios/         fable rule trigger + opus/fable
                                 boundary prompts
```
