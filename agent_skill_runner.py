import json
import os
import sys
from pathlib import Path

from ms_agent.agent import create_agent_skill, AgentSkill
from ms_agent.skill.prompts import (
    PROMPT_SKILL_PLAN,
    PROMPT_SKILL_TASKS,
    PROMPT_TASKS_IMPLEMENTATION,
    SCRIPTS_IMPLEMENTATION_FORMAT,
)


def build_agent() -> AgentSkill:
    base_dir = Path(__file__).parent.resolve()
    skills_dir = str(base_dir / "skills")
    work_dir = str(base_dir / "temp_workspace")
    os.makedirs(work_dir, exist_ok=True)

    model = "qwq-32b"
    api_key = "xxxx"
    base_url = "xxxx"

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY or MS_AGENT_API_KEY must be set")

    agent = create_agent_skill(
        skills=skills_dir,
        model=model,
        api_key=api_key,
        base_url=base_url,
        stream=True,          # AgentSkill._call_llm expects streaming
        enable_thinking=False,
        max_tokens=8192,
        work_dir=work_dir,
        use_sandbox=False,    # we are NOT executing here
    )
    return agent


def plan_only(agent: AgentSkill, query: str) -> str:
    """
    Use ms-agent as a planner only:
    - retrieve relevant skill
    - PLAN
    - TASKS
    - IMPLEMENTATION
    Return ONLY the IMPLEMENTATION text (final step-by-step instructions).
    """

    # 1) Retrieve relevant skills
    relevant_skills = agent.retriever.retrieve(
        query=query,
        method="semantic",
        top_k=5,
    )
    if not relevant_skills:
        return (
            "No relevant skills found for this query. "
            "Please rephrase or ensure you refer to an existing skill."
        )

    top_skill_key, top_skill, score = relevant_skills[0]
    skill = top_skill  # SkillSchema

    # 2) Build skill context
    skill_context = agent._build_skill_context(skill)  # type: ignore[attr-defined]

    skill_md_context = (
        "\n\n<!-- SKILL_MD_CONTEXT -->\n" + skill_context.skill.content.strip()
    )
    reference_context = (
        "\n\n<!-- REFERENCE_CONTEXT -->\n"
        + "\n".join(
            [
                json.dumps(
                    {
                        "name": ref.get("name", ""),
                        "path": ref.get("path", ""),
                        "description": ref.get("description", ""),
                    },
                    ensure_ascii=False,
                )
                for ref in skill_context.references
            ]
        )
    )
    script_context = (
        "\n\n<!-- SCRIPT_CONTEXT -->\n"
        + "\n".join(
            [
                json.dumps(
                    {
                        "name": script.get("name", ""),
                        "path": script.get("path", ""),
                        "description": script.get("description", ""),
                    },
                    ensure_ascii=False,
                )
                for script in skill_context.scripts
            ]
        )
    )
    resource_context = (
        "\n\n<!-- RESOURCE_CONTEXT -->\n"
        + "\n".join(
            [
                json.dumps(
                    {
                        "name": res.get("name", ""),
                        "path": res.get("path", ""),
                        "description": res.get("description", ""),
                    },
                    ensure_ascii=False,
                )
                for res in skill_context.resources
            ]
        )
    )

    # 3) PLAN
    prompt_skill_plan = PROMPT_SKILL_PLAN.format(
        query=query,
        skill_md_context=skill_md_context,
        reference_context=reference_context,
        script_context=script_context,
        resource_context=resource_context,
    )
    plan_text = agent._call_llm(  # type: ignore[attr-defined]
        user_prompt=prompt_skill_plan,
        stream=agent.stream,
    )

    # 4) TASKS
    prompt_skill_tasks = PROMPT_SKILL_TASKS.format(
        skill_plan_context=plan_text,
    )
    tasks_text = agent._call_llm(  # type: ignore[attr-defined]
        user_prompt=prompt_skill_tasks,
        stream=agent.stream,
    )

    # 5) IMPLEMENTATION (do NOT execute)
    script_contents = "\n\n".join(
        [
            "<!-- " + script.get("path", "") + " -->\n" + script.get("content", "")
            for script in skill_context.scripts
            if script.get("name", "") in tasks_text
        ]
    )
    reference_contents = "\n\n".join(
        [
            "<!-- " + ref.get("path", "") + " -->\n" + ref.get("content", "")
            for ref in skill_context.references
            if ref.get("name", "") in tasks_text
        ]
    )
    resource_contents = "\n\n".join(
        [
            "<!-- " + res.get("path", "") + " -->\n" + res.get("content", "")
            for res in skill_context.resources
            if res.get("name", "") in tasks_text
        ]
    )

    prompt_tasks_implementation = PROMPT_TASKS_IMPLEMENTATION.format(
        script_contents=script_contents,
        reference_contents=reference_contents,
        resource_contents=resource_contents,
        skill_tasks_context=tasks_text,
        scripts_implementation_format=SCRIPTS_IMPLEMENTATION_FORMAT,
    )
    impl_text = agent._call_llm(  # type: ignore[attr-defined]
        user_prompt=prompt_tasks_implementation,
        stream=agent.stream,
    )

    # We return ONLY IMPLEMENTATION text.
    return impl_text.strip()


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "missing query arg"}))
        return

    query = sys.argv[1]

    try:
        agent = build_agent()
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"init error: {e}"}))
        return

    try:
        # Redirect all streaming output to stderr so stdout is clean JSON
        orig_stdout = sys.stdout
        sys.stdout = sys.stderr
        try:
            implementation = plan_only(agent, query)
        finally:
            sys.stdout = orig_stdout

        print(json.dumps({"ok": True, "result": implementation}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"run error: {e}"}))


if __name__ == "__main__":
    main()
