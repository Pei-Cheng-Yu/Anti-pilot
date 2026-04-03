import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from app.langgraph.planner.graphs.generate_roadmap.graph import build_planner_graph
from app.langgraph.planner.schema.entities import GoalSpec, LearningProfile
from app.lib.supabase import get_supabase_client

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

# Initialize Supabase client
supabase = get_supabase_client()


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
    Starts the LangGraph planner to generate a tailored roadmap and persists it to Supabase.
    """
    roadmap_id = str(uuid.uuid4())

    planner = build_planner_graph()

    initial_state = {
        "goal_spec": request.goal_spec,
        "learning_profile": request.learning_profile,
        "roadmap_id": roadmap_id,
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

        roadmap_data = final_state["roadmap"].model_dump()
        milestones_data = [m.model_dump() for m in final_state["milestones"]]
        skillpaths_data = [s.model_dump() for s in final_state["skillpaths"]]

        supabase.table("roadmaps").insert(roadmap_data).execute()

        if milestones_data:
            supabase.table("milestones").insert(milestones_data).execute()

        if skillpaths_data:
            supabase.table("skillpaths").insert(skillpaths_data).execute()

        return {
            "roadmap_id": roadmap_id,
            "roadmap": final_state["roadmap"],
            "milestones": final_state["milestones"],
            "skillpaths": final_state["skillpaths"],
        }
    except Exception as e:
        import traceback

        print(f"Error in create_goal: {e}")
        # Print the detailed traceback for debugging
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/roadmaps/{roadmap_id}")
async def get_roadmap(roadmap_id: str):
    """
    Fetches a roadmap and its associated milestones and skillpaths from Supabase.
    """
    try:
        roadmap_res = (
            supabase.table("roadmaps")
            .select("*")
            .eq("roadmap_id", roadmap_id)
            .single()
            .execute()
        )
        if not roadmap_res.data:
            raise HTTPException(status_code=404, detail="Roadmap not found")

        milestones_res = (
            supabase.table("milestones")
            .select("*")
            .eq("roadmap_id", roadmap_id)
            .order("order_index")
            .execute()
        )

        skillpaths_res = (
            supabase.table("skillpaths")
            .select("*")
            .eq("roadmap_id", roadmap_id)
            .execute()
        )

        return {
            "roadmap": roadmap_res.data,
            "milestones": milestones_res.data,
            "skillpaths": skillpaths_res.data,
        }
    except Exception as e:
        print(f"Error in get_roadmap: {e}")
        # Check if it's a 404 from Supabase
        if "JSON object could not be decoded" in str(e) or "PGRST116" in str(e):
            raise HTTPException(status_code=404, detail="Roadmap not found")
        raise HTTPException(status_code=500, detail=str(e))


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
