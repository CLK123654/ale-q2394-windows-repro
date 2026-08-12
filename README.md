# Q2394 Windows reproduction

This public repository contains one Helm task and its independent Windows workflow. The task files are synthetic and contain no Lark credentials, attachment tokens, private backups, or temporary download links.

The workflow uses Helm on windows-2025. Reference generation and formal verification are separate runs. Formal verification rebuilds the delivery in two clean directories, runs each path twice, applies one meaningful input change, checks one fail-closed case, and compares every Reference member.
