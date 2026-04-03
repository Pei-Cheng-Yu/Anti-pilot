import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from app.langgraph.planner.graphs.generate_roadmap.graph import build_planner_graph
from app.langgraph.planner.schema.entities import GoalSpec, LearningProfile

load_dotenv()

app = FastAPI(title="AntiCopilot Unified API", version="0.1.0")

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for PoC
roadmaps_db = {}


class CreateGoalRequest(BaseModel):
    goal_spec: GoalSpec
    learning_profile: LearningProfile


class StruggleSignal(BaseModel):
    roadmap_id: str
    milestone_id: str
    skillpath_id: str
    code_context: str
    diagnostic_message: str


@app.get("/")
async def root():
    return {"status": "online", "message": "AntiCopilot API is running"}


@app.post("/v1/goals")
async def create_goal(request: CreateGoalRequest):
    """
    Starts the LangGraph planner to generate a tailored roadmap.
    """
    roadmap_uuid = str(uuid.uuid4())

    planner = build_planner_graph()

    initial_state = {
        "goal_spec": request.goal_spec,
        "learning_profile": request.learning_profile,
        "roadmap_uuid": roadmap_uuid,
        "roadmap": None,
        "milestones": [],
        "skillpaths": [],
        "milestone_revision_count": 0,
        "skillpath_drafts": [],
        "skillpaths_review": [],
        "skillpath_revisions": [],
    }

    try:
        final_state = planner.invoke(initial_state)

        # Store in our temporary DB
        roadmaps_db[roadmap_uuid] = {
            "roadmap": final_state["roadmap"],
            "milestones": final_state["milestones"],
            "skillpaths": final_state["skillpaths"],
        }

        return {
            "roadmap_id": roadmap_uuid,
            "roadmap": final_state["roadmap"],
            "milestones": final_state["milestones"],
            "skillpaths": final_state["skillpaths"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/roadmaps/{roadmap_id}")
async def get_roadmap(roadmap_id: str):
    if roadmap_id not in roadmaps_db:
        # Fallback for mock data testing
        if roadmap_id == "full-stack-dev":
            return {
                "roadmap": {
                    "roadmap_id": "full-stack-dev",
                    "title": "Full-Stack Dev",
                    "summary": "Mastering React, Node, and Postgres",
                },
                "milestones": [
                    {
                        "milestone_id": "m1",
                        "title": "Advanced State Management",
                        "objective": "Handle complex state safely",
                    }
                ],
                "skillpaths": [
                    {
                        "skillpath_id": "s1",
                        "milestone_id": "m1",
                        "title": "React Context API Patterns",
                        "description": "Deep dive into Context providers",
                        "learning_objectives": ["Create and consume context"],
                    },
                    {
                        "skillpath_id": "s2",
                        "milestone_id": "m1",
                        "title": "The useReducer pattern",
                        "description": "Using reducers instead of state",
                        "learning_objectives": ["Write pure reducers"],
                    },
                ],
            }
        raise HTTPException(status_code=404, detail="Roadmap not found")
    return roadmaps_db[roadmap_id]


@app.post("/v1/signals/struggle")
async def report_struggle(signal: StruggleSignal):
    """
    Receives struggle signals from VS Code and generates a tutoring hint.
    """
    # TODO: Implement AI Tutoring logic using the backend's LLM components
    return {
        "hint": f"It looks like you're struggling with {signal.skillpath_id}. Have you considered checking the documentation for the diagnostic: {signal.diagnostic_message}?",
        "action_required": True,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
