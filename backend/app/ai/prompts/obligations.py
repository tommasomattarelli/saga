from xml.sax.saxutils import escape

from app.ai.prompts.loader import template
from app.ai.tools.dm_tools import get_tool


def compose_obligations(allowed: set[str]) -> str:
    blocks: list[str] = []
    for name in sorted(allowed):
        tool = get_tool(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")
        text = template("tool_obligations", tool.obligation)
        blocks.append(f'<obligation tool="{escape(name)}">\n{text}\n</obligation>')
    return "\n".join(blocks)
