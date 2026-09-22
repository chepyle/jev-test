"""Minimal patches so coastalcph/lex-glue experiments run on a current Hub and transformers.

1. Load the pinned Parquet release (coastalcph/lex_glue @ REVISION) instead of the retired
   `lex_glue` loading script, so BERT sees exactly the rows Jev was scored on.
2. Save raw test logits (test_logits.npy) next to upstream's test_predictions.csv, so paired
   analysis can use probabilities, not only thresholded labels.
3. CaseHOLD: replace the removed `trainer.train(model_path=...)` with checkpoint resume, and
   drop its non-empty-output-dir guard (the other scripts already allow resuming).
5. ECtHR/SCOTUS/UNFAIR-ToS: upstream writes test_predictions.csv from `predictions[0]`,
   assuming the tuple that transformers 4.9 returned; 4.44 returns a bare array, so accept both.
4. ECtHR/SCOTUS: load BERT with eager attention. Upstream's HierarchicalBert encodes
   all-padding segments; transformers >= 4.41 defaults BERT to SDPA, which returns NaN for
   a fully masked segment and poisons every logit (verified: `modal run
   bert/lexglue_modal.py::trace`). Upstream's transformers 4.9 only had eager attention.

Hyperparameters, models, metrics, and early stopping are untouched. Every patch must apply
exactly once, or this script fails.
"""

import re
import sys
from pathlib import Path

REVISION = "c23fdff1a6bf74e0e1a71cb86f1e781d37da888c"
root = Path(sys.argv[1])


def patch(path: Path, old: str, new: str, count: int | None = None, regex: bool = False) -> None:
    text = path.read_text()
    found = len(re.findall(old, text)) if regex else text.count(old)
    if found == 0 or (count is not None and found != count):
        raise SystemExit(f"{path.name}: expected {count or '>0'} matches of {old!r}, found {found}")
    text = re.sub(old, new, text) if regex else text.replace(old, new)
    path.write_text(text)


experiments = root / "experiments"
for name in ("ecthr", "scotus", "eurlex", "ledgar", "unfair_tos"):
    path = experiments / f"{name}.py"
    if "data_dir='data'" in path.read_text():
        patch(path, "data_dir='data', ", "", count=3)
    patch(path, 'load_dataset("lex_glue", ', 'load_dataset("coastalcph/lex_glue", ', count=3)
    patch(path, "split=", f'revision="{REVISION}", split=', count=3)

for name in ("ecthr", "scotus"):
    patch(
        experiments / f"{name}.py",
        "model = AutoModelForSequenceClassification.from_pretrained(\n"
        "            model_args.model_name_or_path,\n",
        "model = AutoModelForSequenceClassification.from_pretrained(\n"
        "            model_args.model_name_or_path,\n"
        '            attn_implementation="eager",\n',
        count=1,
    )

for name in ("ecthr", "scotus", "unfair_tos"):
    patch(
        experiments / f"{name}.py",
        "for index, pred_list in enumerate(predictions[0]):",
        "for index, pred_list in enumerate("
        "predictions[0] if isinstance(predictions, tuple) else predictions):",
        count=1,
    )

helpers = experiments / "casehold_helpers.py"
patch(
    helpers,
    "datasets.load_dataset('lex_glue', task)",
    f"datasets.load_dataset('coastalcph/lex_glue', task, revision='{REVISION}')",
    count=1,
)
patch(
    helpers,
    "datasets.load_dataset('lex_glue')",
    f"datasets.load_dataset('coastalcph/lex_glue', 'case_hold', revision='{REVISION}')",
    count=1,
)

case_hold = experiments / "case_hold.py"
patch(
    case_hold,
    r"trainer\.train\(\n\t+model_path=model_args\.model_name_or_path if os\.path\.isdir\("
    r"model_args\.model_name_or_path\) else None\n\t+\)",
    "trainer.train(resume_from_checkpoint=get_last_checkpoint(training_args.output_dir) "
    "if os.path.isdir(training_args.output_dir) else None)",
    regex=True,
)
patch(
    case_hold,
    '\t\traise ValueError(\n\t\t\tf"Output directory ({training_args.output_dir}) already exists '
    'and is not empty. Use --overwrite_output_dir to overcome."\n\t\t)',
    "\t\tpass  # resume: trainer.train continues from the last checkpoint",
    count=1,
)
text = case_hold.read_text()
if "get_last_checkpoint" not in text.split("def main")[0]:
    case_hold.write_text("from transformers.trainer_utils import get_last_checkpoint\n" + text)

for name in ("ecthr", "scotus", "eurlex", "ledgar", "unfair_tos", "case_hold"):
    path = experiments / f"{name}.py"
    patch(
        path,
        r"(?m)^(\s*)(predictions, labels, metrics = trainer\.predict\(predict_dataset, "
        r'metric_key_prefix="predict"\))$',
        r"\1\2\n\1np.save(os.path.join(training_args.output_dir, 'test_logits.npy'), "
        r"predictions[0] if isinstance(predictions, tuple) else predictions)",
        regex=True,
    )
    if "import numpy as np" not in path.read_text():
        path.write_text("import numpy as np\n" + path.read_text())

print("patched", root)
