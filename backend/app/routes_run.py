import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.graph import create_plan, stream_run

router = APIRouter()


class PlanItem(BaseModel):
    q: str = Field(min_length=3, max_length=300)
    source: Literal["docs", "web"] = "docs"


class PlanRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=500)


class RunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=500)
    plan: list[PlanItem] | None = Field(default=None, max_length=4)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _events(goal: str, plan):
    final = {}
    try:
        for agent, delta in stream_run(goal, plan):
            final.update(delta)
            message = delta["trace"][-1]["message"] if delta.get("trace") else ""
            yield _sse({"type": "step", "agent": agent, "message": message})
        yield _sse(
            {
                "type": "done",
                "report": final.get("report", ""),
                "approved": final.get("approved", False),
                "drafts": final.get("drafts", 0),
                "evidence": final.get("evidence", []),
            }
        )
    except Exception as e:
        yield _sse({"type": "error", "message": str(e)})


@router.post("/plan")
def make_plan(req: PlanRequest):
    try:
        return {"plan": create_plan(req.goal)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/run")
def run_crew(req: RunRequest):
    plan = [p.model_dump() for p in req.plan] if req.plan else None
    return StreamingResponse(_events(req.goal, plan), media_type="text/event-stream")