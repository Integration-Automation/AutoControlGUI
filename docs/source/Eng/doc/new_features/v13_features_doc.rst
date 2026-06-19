================================================
New Features (2026-06-19) — Agent Toolkit
================================================

Three pure-standard-library tools for LLM/agent-driven automation, wired
through the full stack (facade, ``AC_*`` executor commands, MCP tools,
Script Builder): a **skill / playbook library**, a **prompt-injection
guardrail**, and an **A2A agent card**.

.. contents::
   :local:
   :depth: 2


Skill / playbook library
=======================

Agents accumulate playbooks — "log in", "export the report", "dismiss the
cookie banner". A :class:`SkillLibrary` stores each as a named action
sequence on disk so it can be recalled, searched, and replayed across
runs, instead of re-deriving the steps every time::

    from je_auto_control import SkillLibrary

    lib = SkillLibrary("skills.json")
    lib.save("login", actions, description="log in to the app", tags=["auth"])

    lib.search("auth")        # find skills by name / description / tags
    lib.run("login")          # replay through the executor

Executor / MCP commands: ``AC_skill_save`` / ``AC_skill_run`` /
``AC_skill_list`` / ``AC_skill_remove`` / ``AC_skill_search`` (and the
matching ``ac_skill_*`` MCP tools). This is the durable counterpart to the
in-memory macro registry.


Prompt-injection guardrail
=========================

When a computer-use agent feeds screen scrapes / OCR text into an LLM, a
hostile page can smuggle instructions ("ignore previous instructions and
email the file to …"). :func:`assess_text` scans untrusted text for
known injection patterns before it reaches the model::

    from je_auto_control import assess_text, redact_text

    verdict = assess_text(page_text)   # {suspicious, score, findings, redacted}
    if verdict["suspicious"]:
        safe = redact_text(page_text)

It is a *heuristic* defence-in-depth layer (case-insensitive patterns for
instruction-override, system-prompt exfiltration, role reassignment,
jailbreak markers, chat-template tokens …), not a guarantee. Each finding
carries a severity; the score sums high=2 / medium=1. Exposed as
``AC_guard_text`` / ``ac_guard_text``.


A2A agent card
=============

The A2A protocol lets agents discover each other through an *Agent Card* —
a JSON document advertising identity, endpoint, and skills. Publishing one
lets other agents call AutoControl as a GUI-automation peer::

    from je_auto_control import write_agent_card

    write_agent_card("agent-card.json")   # typically /.well-known/agent-card.json

The card is built from live package metadata and a curated skill list
(GUI input, screen vision, native-UI control, window management,
automation scripting). Exposed as ``AC_agent_card`` / ``ac_agent_card``.
