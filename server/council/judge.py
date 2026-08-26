"""The blind judge.

`judge()` is never given a model id. It receives (label, answer) pairs and nothing else, so it
cannot leak a name into the prompt even by mistake - blindness is a property of the signature
rather than a rule someone has to remember. That matters because judges drift toward flattering
whichever model shares their family, and a judge that knows the names will do it.
"""

from __future__ import annotations

import logging
import re

from server.models.council import CouncilVerdict, Ranking
from server.models.params import SamplingParams
from server.providers.base import ModelProvider, PromptMessage, Token

log = logging.getLogger(__name__)

DEFAULT_RUBRIC = "Accuracy first, then whether it actually answers the question, then concision."

PROMPT = """You are judging anonymous answers to one question. You do not know who wrote them and
must not guess.

Question: {question}

Rubric: {rubric}

Answers:
{answers}

Reply in exactly this shape, nothing else:

RANKING: <labels best to worst, separated by ">">
DISAGREEMENT: <one paragraph on where the answers actually differ, or "none">
SYNTHESIS: <the best answer you can give, drawing on whichever answers were right>
"""

RANKING_LINE = re.compile(r"^RANKING:\s*(.+)$", re.MULTILINE)
DISAGREEMENT_LINE = re.compile(r"^DISAGREEMENT:\s*(.*?)(?=^SYNTHESIS:|\Z)", re.MULTILINE | re.S)
SYNTHESIS_LINE = re.compile(r"^SYNTHESIS:\s*(.*)\Z", re.MULTILINE | re.S)


def render_answers(answers: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"[{label}]\n{content.strip()}" for label, content in answers)


def parse(raw: str, labels: list[str]) -> CouncilVerdict:
    """Defensive parsing: a judge that ignores the format yields an empty ranking, not nonsense."""
    verdict = CouncilVerdict()
    if match := RANKING_LINE.search(raw):
        ordered = [
            token.strip().strip("[]").upper()
            for token in re.split(r"[>,]", match.group(1))
            if token.strip()
        ]
        seen: set[str] = set()
        for position, label in enumerate(ordered, start=1):
            if label in labels and label not in seen:
                seen.add(label)
                verdict.ranking.append(Ranking(label=label, rank=position))
    if match := DISAGREEMENT_LINE.search(raw):
        verdict.disagreements = match.group(1).strip()
    if match := SYNTHESIS_LINE.search(raw):
        verdict.synthesis = match.group(1).strip()
    return verdict


async def judge(
    provider: ModelProvider,
    *,
    model_id: str,
    ctx_len: int,
    question: str,
    rubric: str,
    answers: list[tuple[str, str]],
) -> CouncilVerdict:
    """`answers` is (label, content). No model identity reaches this function, by design."""
    if not answers:
        return CouncilVerdict(judge_model_id=model_id)

    prompt = PROMPT.format(
        question=question,
        rubric=rubric or DEFAULT_RUBRIC,
        answers=render_answers(answers),
    )
    params = SamplingParams(seed=3, temperature=0.2, max_tokens=600, n_probs=0)
    chunks: list[str] = []
    try:
        async for item in provider.stream(
            [PromptMessage(role="user", content=prompt)],
            params,
            model_id=model_id,
            ctx_len=ctx_len,
        ):
            if isinstance(item, Token):
                chunks.append(item.text)
    except Exception as exc:  # noqa: BLE001 - no verdict is better than a fabricated one
        log.warning("council: judging failed: %s", exc)
        return CouncilVerdict(judge_model_id=model_id)

    verdict = parse("".join(chunks), [label for label, _ in answers])
    verdict.judge_model_id = model_id
    return verdict
