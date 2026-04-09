from app.mcp.tools.goal import goal_mcp
from app.mcp.tools.learning_profile import learning_profile_mcp
from app.mcp.tools.roadmap import roadmap_mcp
from fastmcp import FastMCP

mcp = FastMCP("anti-pilot")

mcp.mount(goal_mcp, prefix="goal")
mcp.mount(learning_profile_mcp, prefix="learning_profile")
mcp.mount(roadmap_mcp, prefix="roadmap")

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8001, path="/mcp")
