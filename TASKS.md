# Project Roadmap: Advanced Workflow SPA

## System Rules

- Review the entire roadmap before starting any task to ensure alignment with project goals and dependencies.
- All tasks are assigned to a single agent.
- Tasks use numbers: `1 [ ] Task`
- Subtasks use letters: `1a [ ] Subtask`
- Status indicators: `[ ]` (Free), `[~]` (In Progress), `[x]` (Finished)
- Agents in `RELAXING` state will be assigned the next available main task.
- Agents in `WAITING_FOR_INPUT` are locked until PRs are merged by human intervention and are manually reset.

---

## 1 Backend & API Infrastructure

1 [ ] Define API Endpoints & Models
  1a [ ] Design OpenAPI spec for all endpoints (GET/POST/PUT/DELETE)
  1b [ ] Define Pydantic models for workflows and user preferences
  1c [ ] Design DB schema (PostgreSQL/Supabase) or JSON/YAML file structure
2 [ ] Implement Core Endpoints
  2a [ ] Implement CRUD logic for workflows
  2b [ ] Implement pinning and favorites logic
  2c [ ] Implement export/import and backup/restore logic
3 [ ] NIM/Cloud Sync Implementation
  3a [ ] Implement /run endpoint for local vs NIM VM execution
  3b [ ] Handle NIM VM API authentication and error states
4 [ ] Security & Validation
  4a [ ] Add JWT/Session authentication
  4b [ ] Finalize Pydantic input validation layers
5 [ ] Backend Testing
  5a [ ] Write unit tests for endpoints and models
  5b [ ] Perform integration tests (DB and NIM VM)

## 2 Frontend Development (React/Vite)

6 [ ] UI/UX Design & Architecture
  6a [ ] Define Design System using Tailwind and Vault-Themes
  6b [ ] Create wireframes for Category Sidebar and Workflow List
7 [ ] Core Component Implementation
  7a [ ] Build responsive Category Sidebar
  7b [ ] Build Sortable/Filterable Workflow List
  7c [ ] Implement Modals for Create/Import/Export/Restore
8 [ ] State Management (Redux/Zod)
  8a [ ] Setup Redux store for workflows and UI state
  8b [ ] Implement Zod schemas for client-side validation
9 [ ] API Integration
  9a [ ] Connect Axios/Fetch to backend endpoints
  9b [ ] Implement global error handling and loading states
10 [ ] Testing & Optimization
  10a [ ] Write component unit tests
  10b [ ] Perform E2E testing with Playwright

## 3 Cross-Cutting Features

11 [ ] NIM VM API Integration
  11a [ ] Build client/server logic for remote execution
  11b [ ] Implement status polling for long-running workflows
12 [ ] Documentation & QA
  12a [ ] Generate Swagger/OpenAPI documentation
  12b [ ] Perform full system audit (Accessibility & Security)
13 [ ] CI/CD & Deployment
  13a [ ] Setup GitHub Actions for Build/Test/Deploy
  13b [ ] Write User & Admin guides
