import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.graph import stream_run

router = APIRouter()


class RunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=500)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _events(goal: str):
    final = {}
    try:
        for agent, delta in stream_run(goal):
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


@router.post("/run")
def run_crew(req: RunRequest):
    return StreamingResponse(_events(req.goal), media_type="text/event-stream")