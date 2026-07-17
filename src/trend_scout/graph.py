"""LangGraph pipeline assembly.

    planner -> researcher -> curator -> writer -> judge -> END
                  |  ^                     ^        |
                  v  | (one replan)        | (<= max_revisions)
               replan­-bump                 revise-bump
"""

from langgraph.graph import END, START, StateGraph

from trend_scout import nodes
from trend_scout.schemas import DigestState


def build_graph():
    graph = StateGraph(DigestState)

    graph.add_node("planner", nodes.planner)
    graph.add_node("researcher", nodes.researcher)
    graph.add_node("replan_bump", nodes.bump_replans)
    graph.add_node("curator", nodes.curator)
    graph.add_node("writer", nodes.writer)
    graph.add_node("judge", nodes.judge)
    graph.add_node("revise_bump", nodes.bump_revisions)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "researcher")
    graph.add_conditional_edges(
        "researcher",
        nodes.route_after_research,
        {"curator": "curator", "replan": "replan_bump"},
    )
    graph.add_edge("replan_bump", "planner")
    graph.add_edge("curator", "writer")
    graph.add_edge("writer", "judge")
    graph.add_conditional_edges(
        "judge",
        nodes.route_after_judge,
        {"approve": END, "revise": "revise_bump"},
    )
    graph.add_edge("revise_bump", "writer")

    return graph.compile()


def run_digest(topics: list[str], config: dict | None = None) -> DigestState:
    """Convenience entrypoint: run the full pipeline for given topics.

    :param config: optional LangGraph run config, e.g. ``{"callbacks": [...]}``.
    """
    app = build_graph()
    return app.invoke(
        {"topics": topics, "replans": 0, "revisions": 0, "events": []}, config=config
    )
