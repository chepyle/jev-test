"""Serve precomputed cross-encoder logits as a System One endpoint for Kev's scorer.

encoder/modal_app.py::predict writes raw per-option logits for every evaluation record,
keyed by request hash. This fits one temperature on decision-v7's calibration partition
(minimum NLL, as Kev fits its shipped temperature) and answers `POST /v1/systemone` by
looking the request up, so `kev.benchmark --remote` scores the encoder exactly as it scores
every other model. A request with no stored logits is an error, never a guess.

    uv run python encoder/replay.py results/kev-encoder/<name>/logits.jsonl --port 8766
        [--temperature 1]
"""

import argparse
import json
import math
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crossenc import to_answers  # noqa: E402

KEV = Path(__file__).resolve().parents[1] / "third_party" / "kev"


def softmax(xs, t):
    m = max(x / t for x in xs)
    e = [math.exp(x / t - m) for x in xs]
    s = sum(e)
    return [v / s for v in e]


def calibration_nll(rows, gold, t):
    total, n = 0.0, 0
    for row in rows:
        for qid, lg in row["logits"].items():
            total -= math.log(max(softmax(lg, t)[gold[(row["id"], qid)]], 1e-12))
            n += 1
    return total / n


def fit_temperature(rows):
    """Grid search in log space, then refine: one scalar, so a grid is exact enough."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from crossenc import label_index

    gold = {}
    with open(KEV / "evals/v7/decision-v7/calibration.jsonl") as fh:
        for line in fh:
            record = json.loads(line)
            for qid, q in record["questions"].items():
                gold[(record["_meta"]["id"], qid)] = label_index(q)
    cal = [r for r in rows if r["suite"] == "decision-v7" and r["split"] == "calibration"]
    grid = [math.exp(x / 50) for x in range(-150, 151)]
    best = min(grid, key=lambda t: calibration_nll(cal, gold, t))
    fine = [best * math.exp(x / 1000) for x in range(-20, 21)]
    best = min(fine, key=lambda t: calibration_nll(cal, gold, t))
    return best, calibration_nll(cal, gold, 1.0), calibration_nll(cal, gold, best), len(gold)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("logits", type=Path)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--temperature", type=float, help="skip the fit and use this value")
    parser.add_argument("--model", default="kev-encoder")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.logits.open()]
    if args.temperature is None:
        t, before, after, n = fit_temperature(rows)
        info = {
            "temperature": t,
            "calibration_nll_raw": before,
            "calibration_nll_fitted": after,
            "calibration_questions": n,
        }
        (args.logits.parent / "temperature.json").write_text(json.dumps(info, indent=2) + "\n")
    else:
        t = args.temperature
    table = {r["key"]: r["logits"] for r in rows}
    print(f"serving {len(table)} requests at temperature {t:.4f} on :{args.port}", flush=True)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["content-length"])))
            from crossenc import request_key

            logits = table.get(request_key(request))
            if logits is None:
                body, status = (
                    json.dumps({"error": "no stored logits for this request"}).encode(),
                    404,
                )
            else:
                probs = {qid: softmax(lg, t) for qid, lg in logits.items()}
                body, status = json.dumps(to_answers(request, probs, args.model)).encode(), 200
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
