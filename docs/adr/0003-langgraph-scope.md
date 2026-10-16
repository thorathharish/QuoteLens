# ADR-0003: LangGraph only where reasoning loops exist
- **Status:** Accepted
- **Context:** LangGraph adds value for tool-calling agents. The analysis pipeline is a fixed sequence of steps.
- **Decision:** Use LangGraph for (a) the copilot ReAct agent and (b) the alternatives-investigation sub-graph. Run the analysis pipeline as an explicit staged job, with progress in Firestore. Human gates are modelled by the project state machine.
- **Consequences:** Easier debugging and observability of the pipeline. Agent graphs stay small and testable with a fake chat model.
