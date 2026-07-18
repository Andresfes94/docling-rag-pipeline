#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

import httpx

from src.evaluation.evaluator import evaluate_all, print_report
from src.llm.client import LLMClient


def check_api(api_url: str) -> bool:
    try:
        resp = httpx.get(f"{api_url}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def check_ollama(model: str) -> bool:
    client = LLMClient(provider="ollama", model=model)
    return client.check_available()


def main():
    parser = argparse.ArgumentParser(description="Evaluate RAG pipeline across test questions")
    parser.add_argument("--model", default="llama3.2", help="Model name (default: llama3.2)")
    parser.add_argument("--provider", default="ollama", choices=["ollama", "lmstudio"], help="LLM provider")
    parser.add_argument("--k", type=int, default=5, help="Number of chunks to retrieve (default: 5)")
    parser.add_argument("--api-url", default="http://localhost:8000", help="RAG pipeline API URL")
    parser.add_argument("--output", default="", help="Path to write JSON results")
    parser.add_argument("--direct", action="store_true", default=True, help="Use direct pipeline calls (faster, no API needed)")
    parser.add_argument("--no-direct", action="store_false", dest="direct", help="Use HTTP API instead of direct pipeline calls")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-question output")
    args = parser.parse_args()

    if not args.direct and not check_api(args.api_url):
        print(f"ERROR: RAG pipeline API at {args.api_url} is not reachable.")
        sys.exit(1)
    if not args.direct:
        print(f"API reachable at {args.api_url}")

    if not check_ollama(args.model):
        print(f"WARNING: Ollama model '{args.model}' may not be available or Ollama is not running.")
        proceed = input("Continue anyway? [y/N]: ")
        if proceed.lower() != "y":
            sys.exit(1)
    else:
        print(f"Ollama model '{args.model}' is available")

    print(f"\nRunning evaluation: model={args.model}, k={args.k} (direct={args.direct}) ...\n")

    metrics = evaluate_all(
        model=args.model,
        provider=args.provider,
        api_url=args.api_url,
        k=args.k,
        use_direct=args.direct,
    )

    report = print_report(metrics)
    print(report)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(metrics, f, indent=2, default=str)
        print(f"\nDetailed JSON written to {args.output}")

    accuracy = metrics["overall_accuracy"]
    rejection = metrics.get("out_of_context_rejection_rate", 0)
    print(f"\nSummary: Accuracy={accuracy:.1f}%  OOC-Rejection={rejection}%  "
          f"Latency={metrics['avg_latency_s']:.2f}s  "
          f"Tokens={metrics['avg_tokens_per_response']}")

    return 0 if accuracy >= 50 else 1


if __name__ == "__main__":
    sys.exit(main())
