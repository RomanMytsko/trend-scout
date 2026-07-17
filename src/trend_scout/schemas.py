"""Pydantic models: agent structured outputs and graph state."""

import operator
import typing

import pydantic


class ResearchPlan(pydantic.BaseModel):
    """Planner output: how to research the requested topics."""

    reasoning: str = pydantic.Field(description="Short reasoning behind the query choice.")
    queries: list[str] = pydantic.Field(
        min_length=2, max_length=6, description="Web search queries covering the topics."
    )


class RawItem(pydantic.BaseModel):
    """A single collected news/article candidate."""

    title: str
    url: str
    source: str
    published: str | None = None
    snippet: str = ""


class CuratedPick(pydantic.BaseModel):
    """Curator's selection of one item with justification."""

    index: int = pydantic.Field(description="Index of the item in the candidate list.")
    relevance: int = pydantic.Field(ge=1, le=5)
    why_it_matters: str = pydantic.Field(description="Why this matters for the audience.")


class CurationResult(pydantic.BaseModel):
    picks: list[CuratedPick] = pydantic.Field(
        description="Best items first. Empty if nothing is relevant."
    )


class JudgeVerdict(pydantic.BaseModel):
    """LLM-as-a-judge rubric scores for the digest draft."""

    relevance: int = pydantic.Field(ge=1, le=5)
    grounding: int = pydantic.Field(ge=1, le=5)
    format_score: int = pydantic.Field(ge=1, le=5)
    feedback: str = pydantic.Field(description="Concrete instructions on what to fix.")

    @property
    def average(self) -> float:
        return (self.relevance + self.grounding + self.format_score) / 3


class DigestState(typing.TypedDict, total=False):
    """Shared LangGraph state passed between nodes."""

    topics: list[str]
    plan: ResearchPlan
    items: list[RawItem]
    curation: CurationResult
    digest: str
    verdict: JudgeVerdict
    replans: int
    revisions: int
    events: typing.Annotated[list[str], operator.add]
