# AGENTS.md

Guidance for AI coding agents working on the GrowQR Admin Portal codebase.

This project is early, but it should be treated as production-bound from the start. We are developing locally now and expect to host the system on AWS later.

## Working Principles

- Read the relevant docs and existing code before changing files.
- Ask for clarification when the prompt is ambiguous or missing important implementation details.
- Do not write code when the requested behavior, target file, or acceptance criteria are unclear.
- Keep implementation choices aligned with the architecture documents.
- Prefer maintainable, production-ready code over quick local-only shortcuts.
- Keep changes scoped to the requested feature or bug.
- Do not introduce unrelated refactors while implementing a feature.
- Do not revert or overwrite user changes unless explicitly asked.

## Code Quality

- Keep module boundaries clean.
- Keep file placement intentional and consistent with the existing project structure.
- Separate data contracts, business logic, infrastructure clients, and command-line entry points.
- Avoid patchwork fixes, hardcoded overrides, and one-off conditionals that only satisfy a single sample file.
- Avoid hidden magic. Configuration should come from environment variables, typed settings, or explicit function parameters.
- Do not hardcode secrets, API keys, local absolute paths, organization IDs, Clerk IDs, or AWS resource names.
- Keep functions small enough to test and reason about.
- Prefer explicit data contracts with Pydantic or typed models when data crosses module boundaries.
- Keep external integrations isolated behind reusable clients/services.

## Testing Expectations

Every meaningful feature should include an appropriate test plan.

Build and maintain a test suite as the project grows:

- Use a test pyramid: many fast unit tests, fewer integration tests, and only essential end-to-end tests.
- Keep tests under a dedicated test directory with clear names and reusable fixtures.
- Use test markers or naming conventions to separate fast tests from slower integration or external-service tests.
- Mock third-party APIs by default; use real services only in explicit integration environments.
- Add regression tests for bugs before or while fixing them.

Use unit tests for:

- schema validation and data normalization
- pure helper functions and deterministic business rules
- permission checks
- request/payload builders
- error handling branches

Use integration tests for:

- third-party service flows with mocked API responses
- Postgres read/write behavior once persistence is introduced
- authentication and authorization boundaries
- bulk workflow boundaries

Do not rely only on manual testing for code that will be reused by APIs, workers, or downstream services.

When adding a feature:

- add or update tests where practical
- run the relevant tests before reporting completion
- mention any tests that could not be run and why

## Database And Persistence

- PostgreSQL is the source-of-truth database target.
- Do not introduce SQLite-specific assumptions.
- Use Postgres-native features where they are part of the design, including `jsonb`, composite keys, foreign keys, and partial unique indexes.
- Store large files in private object storage, not Postgres bytea.
- Store structured flexible data as `jsonb` when the architecture calls for it.
- Avoid speculative indexes until query patterns justify them.

## Data Contracts

- Data contracts should be explicit and validated at module boundaries.
- Schema definitions should be owned by code, not only by prompts, comments, or sample JSON.
- Do not add semantic normalization, inferred values, or automatic data repair unless explicitly requested.
- Do not silently invent missing business data.
- Intermediate outputs should be inspectable before they are used by downstream workflows.

## External Services

- Keep Clerk, OpenAI, AWS, and future storage/database integrations behind small service/client modules.
- Use environment variables for credentials and deployment-specific settings.
- Do not commit real secrets.
- Make network failures explicit and debuggable.
- Prefer retry behavior only where it is safe and bounded.

## Local Development Now, AWS Later

- Local scripts are acceptable while the product is being shaped, but they should not block later migration into APIs/workers.
- Avoid local-only path assumptions.
- Prefer configuration that can work in local shells, containers, CI, and AWS runtime environments.
- Design storage abstractions with future S3/private object storage in mind.
- Design long-running or heavy processing with future worker queues in mind.

## Documentation

- Update implementation notes when a feature boundary changes.
- Keep docs concrete and current.
- Document commands needed to run scripts, tests, and local workflows.
- Do not let code behavior drift away from `architecture.md` and `admin_portal implimentation.md` without updating the docs.

## Done Means

A task is not done just because code was written.

For a feature to be considered done:

- the relevant code path is implemented
- the data contract is clear
- tests are added or a clear reason is given for not adding them yet
- the code compiles or runs in the expected local workflow
- configuration requirements are documented
- known limitations are called out
