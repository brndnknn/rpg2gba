"""Headless ROM playtesting via libmgba-py.

Feasibility study + spike narrative: reference/findings/
mgba_automation_feasibility_2026-07-17.md. The mGBA Python bindings are not
pip-installable; run scripts/fetch_libmgba.py once per venv to install them.

Modules:
    emulator  - headless core wrapper + poll-state input primitives
    symbols   - linker-map symbol lookup + static-address recovery via objdump
    offsets   - struct offsets/constants probe-compiled from the engine headers
    scenarios - scripted playthroughs (one function per scenario)
    stamp     - embedded-save ROM stamping (single-file review artifacts)
"""
