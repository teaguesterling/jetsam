"""MCP tools must publish the NAMES of the keys they return.

FastMCP derives `outputSchema` from the return annotation. `dict[str, Any]`
becomes:

    {"additionalProperties": true, "type": "object"}

which tells a caller it gets *an object* and nothing further, so a
programmatic consumer has to guess the keys.

Measured by a session driving four local models against this suite through
lackpy: 0/24 correct while 17/24 called the correct tool. `log` was the one
tool that already carried a usable schema, and annotating it was the single
cleanly traceable fix in their prototype — a program that had been crashing
on `'list' object has no attribute 'split'` iterated it correctly once the
shape was published.

The shapes here matter more than most, because they encode jetsam's central
invariant: `save` returns a PLAN and commits nothing; `confirm` executes it.
A caller that cannot see `plan_id` in the response has no reason to suspect a
second call is required — which is exactly the reported failure, a model
calling save and stopping, 4/4 trials.

See #25.
"""

import pytest

pytest.importorskip("mcp.server.fastmcp")


@pytest.fixture(scope="module")
def tools():
    from mcp.server.fastmcp import FastMCP

    from jetsam.mcp.tools import register_tools

    server = FastMCP("schema-test")
    register_tools(server)
    return server._tool_manager._tools


def _properties(tool):
    """Every property name discoverable in the published schema.

    Walks the whole document rather than reading a single `properties` block:
    a union return is emitted as `anyOf` over `$ref`s into `$defs`, and a
    non-object return is wrapped in `{"result": ...}`. All of those are
    resolvable by a schema consumer, so all of them count as published — the
    thing being asserted is that a caller can discover the key names at all,
    not the particular nesting pydantic chose.
    """
    schema = tool.output_schema
    assert schema is not None, "tool publishes no output_schema"

    found = {}

    def walk(node):
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict):
                for k, v in props.items():
                    if k != "result":
                        found[k] = v
            for key, value in node.items():
                if key != "properties":
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return found


# Keys read from Plan.to_dict / ExecutionResult.to_dict, not from docs.
PLAN_TOOLS = ["save", "sync", "ship", "switch", "start", "finish", "tidy",
              "release", "show_plan"]


@pytest.mark.parametrize("name", PLAN_TOOLS)
def test_plan_tools_publish_plan_id(name, tools):
    """`plan_id` is the handle confirm() needs — the invariant made visible."""
    props = _properties(tools[name])
    assert "plan_id" in props, (
        f"{name} publishes no key names (got {sorted(props) or 'nothing'}); a "
        f"caller cannot see that it returns a plan requiring confirm()"
    )


@pytest.mark.parametrize("name", PLAN_TOOLS)
def test_plan_tools_publish_steps_and_verb(name, tools):
    props = _properties(tools[name])
    assert "steps" in props
    assert "verb" in props


def test_confirm_publishes_execution_shape(tools):
    props = _properties(tools["confirm"])
    for key in ("plan_id", "status", "results", "completed_steps", "total_steps"):
        assert key in props, f"confirm omits {key}: got {sorted(props)}"


def test_git_publishes_its_streams(tools):
    props = _properties(tools["git"])
    for key in ("ok", "stdout", "stderr", "returncode"):
        assert key in props, f"git omits {key}: got {sorted(props)}"


def test_cancel_publishes_its_shape(tools):
    props = _properties(tools["cancel"])
    assert {"ok", "id"} <= set(props), sorted(props)


def test_log_still_declares_an_array(tools):
    """Already correct before this change — guard against regressing it."""
    schema = tools["log"].output_schema
    assert schema is not None
    assert "array" in str(schema), schema
