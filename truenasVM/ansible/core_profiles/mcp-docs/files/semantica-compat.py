"""Correct the edge-count fallback in the pinned Semantica 0.7.0 MCP tool.

ContextGraph has an edges collection but no edge_count() method. The upstream
summary therefore reports zero even for saved and restored relationships.
Fail the image build if upgrading changes the source that this fix targets.
"""

from importlib.metadata import version
from pathlib import Path
from sysconfig import get_path

if version("semantica") != "0.7.0":
    raise RuntimeError("Review the summary compatibility fix before upgrading Semantica")

source = Path(get_path("purelib")) / "semantica_mcp/mcp/tools/graph.py"
original = source.read_text()
old = "        edge_count = 0\n        if hasattr(graph, \"edge_count\"):"
new = "        edge_count = len(graph.edges)\n        if hasattr(graph, \"edge_count\"):"
if original.count(old) != 1:
    raise RuntimeError("Semantica summary source changed; review the compatibility fix")
source.write_text(original.replace(old, new))
