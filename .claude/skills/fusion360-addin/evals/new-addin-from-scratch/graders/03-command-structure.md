---
type: llm
focus: trace
weight: 1
---

The command module reads inputs with isValidExpression checks, has a preview handler that builds and sets args.isValidResult = True, saves settings only when the dialog completed (CompletedTerminationReason), builds the panels inside a newly created component, and cleans up (deletes the occurrence) when the build fails.
