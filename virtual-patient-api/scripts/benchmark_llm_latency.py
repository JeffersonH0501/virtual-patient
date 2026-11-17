#!/usr/bin/env python3
"""Compare configured normal and mini chat deployment response latency."""

import argparse
from statistics import mean, median
from time import perf_counter

from app.core.azure_openai import LLMVariant, create_chat_model, deployment_for


PROMPT = "Reply with exactly one word: ready."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5, help="Requests per deployment (default: 5)")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    return args


def main() -> None:
    args = parse_args()
    print("This benchmark makes billable Azure OpenAI requests using a fixed, synthetic prompt.")
    print(f"Normal: {deployment_for(LLMVariant.NORMAL)}")
    print(f"Mini:   {deployment_for(LLMVariant.MINI)}")

    models = {
        LLMVariant.NORMAL: create_chat_model(variant=LLMVariant.NORMAL, temperature=0, max_tokens=8),
        LLMVariant.MINI: create_chat_model(variant=LLMVariant.MINI, temperature=0, max_tokens=8),
    }
    samples: dict[LLMVariant, list[float]] = {variant: [] for variant in LLMVariant}

    for run in range(args.runs):
        order = (LLMVariant.NORMAL, LLMVariant.MINI)
        if run % 2:
            order = tuple(reversed(order))
        for variant in order:
            started = perf_counter()
            models[variant].invoke(PROMPT)
            elapsed_ms = (perf_counter() - started) * 1000
            samples[variant].append(elapsed_ms)
            print(f"Run {run + 1} {variant.value}: {elapsed_ms:.0f} ms")

    summaries = {
        variant: {"mean": mean(values), "median": median(values)}
        for variant, values in samples.items()
    }
    for variant in (LLMVariant.NORMAL, LLMVariant.MINI):
        values = samples[variant]
        summary = summaries[variant]
        print(
            f"{variant.value}: mean {summary['mean']:.0f} ms, "
            f"median {summary['median']:.0f} ms, "
            f"range {min(values):.0f}-{max(values):.0f} ms"
        )

    difference = summaries[LLMVariant.NORMAL]["median"] - summaries[LLMVariant.MINI]["median"]
    faster = "mini" if difference > 0 else "normal" if difference < 0 else "equal"
    print(f"Median difference (normal - mini): {difference:+.0f} ms; faster: {faster}.")
    print("Times include network/provider queueing and generation; they are not pure model inference benchmarks.")


if __name__ == "__main__":
    main()
