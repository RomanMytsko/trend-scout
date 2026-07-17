"""CLI entrypoint: ``trend-scout "topic 1" "topic 2" [-o digest.md]``."""

import argparse
import logging
import sys

from trend_scout import graph

DEFAULT_TOPICS = [
    "multi-agent orchestration",
    "MCP and A2A protocols",
    "LangGraph and agent frameworks",
    "context engineering",
]


def main() -> None:
    parser = argparse.ArgumentParser(prog="trend-scout", description=__doc__)
    parser.add_argument("topics", nargs="*", default=DEFAULT_TOPICS)
    parser.add_argument("-o", "--out", help="Write digest markdown to this file.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    state = graph.run_digest(list(args.topics))

    print("\n--- pipeline events ---", file=sys.stderr)
    for event in state.get("events", []):
        print(f"  {event}", file=sys.stderr)
    verdict = state.get("verdict")
    if verdict is not None:
        print(
            f"--- judge: relevance={verdict.relevance} grounding={verdict.grounding} "
            f"format={verdict.format_score} avg={verdict.average:.2f} ---\n",
            file=sys.stderr,
        )

    digest = state.get("digest", "")
    print(digest)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(digest)
        print(f"\nSaved to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
