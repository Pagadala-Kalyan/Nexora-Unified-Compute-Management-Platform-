# NEXORA — BACKEND TASK

## 1. Role

You are responsible for the backend foundation of Nexora.

Your job is to provide the APIs, database, authentication, validation and common backend services required by the other three developers.

You are NOT responsible for implementing the core remote execution, recovery algorithms, or billing logic itself. Those are owned by the feature developers.

---

# 2. Preparation

Before coding:

* Understand the complete Nexora architecture.
* Understand all four Phase 1 features.
* Design the backend architecture.
* Select backend technology.
* Select database.
* Define API conventions.
* Define common data models.
* Define authentication strategy.

---

# 3. Core Backend Responsibilities

Implement:

### Authentication

* Registration
* Login
* Authentication
* Authorization
* User/session handling

### Database

Create the common database structure required by:

* Users
* Jobs
* Resources
* Checkpoints
* Failures
* Wallets
* Transactions

The exact schema must be finalized collaboratively.

### API Layer

Provide APIs for:

* Authentication
* Jobs
* Resources
* Execution
* Failure/recovery
* Wallet
* Billing

---

# 4. Common Job Model

Create a common job structure containing appropriate fields such as:

* Job ID
* User ID
* Job name
* Job type
* Status
* Requirements
* Assigned resource
* Start time
* End time
* Result
* Cost
* Checkpoint information
* Failure information

The final structure must be agreed with Persons 3 and 4.

---

# 5. API Contract

Create:

`API_CONTRACT.md`

Document every API using:

* Endpoint
* Method
* Authentication
* Request
* Response
* Status codes
* Error format

Example:

`POST /jobs`

Request:

```json
{
  "name": "...",
  "requirements": {}
}
```

Response:

```json
{
  "job_id": "...",
  "status": "QUEUED"
}
```

These are examples only. Final contracts must be agreed by the team.

---

# 6. Collaboration With Person 1

Provide Person 1 with:

* API endpoints
* Request formats
* Response formats
* Authentication method
* Error format
* Status values

Notify the frontend developer before changing an API contract.

---

# 7. Collaboration With Person 3

Coordinate on:

### Remote Execution

* Job creation
* Job status
* Execution result
* Resource assignment

### Resource Pool

* Resource registration
* Resource status
* Resource information
* Resource allocation

Person 3 owns the feature logic.

You provide the backend infrastructure/API required to expose that logic.

---

# 8. Collaboration With Person 4

Coordinate on:

### Failure Recovery

* Failure records
* Checkpoint records
* Recovery status

### Billing

* Usage records
* Wallet records
* Transactions
* Cost information

Person 4 owns the feature logic.

You provide the database/API infrastructure.

---

# 9. Integration Rules

The backend must NOT become a bottleneck.

Before implementing an API:

1. Discuss the requirement with the feature owner.
2. Agree on request/response structure.
3. Document the contract.
4. Implement the API.
5. Provide a test endpoint.
6. Inform the frontend developer.

Do not silently change API structures.

---

# 10. Backend Deliverables

* Backend application
* Database
* Authentication
* API layer
* API documentation
* Data models
* Validation
* Error handling
* Logging
* Environment configuration
* Seed/demo data

---

# 11. Handover

Maintain:

`BACKEND_HANDOVER.md`

Include:

* Backend technology
* How to run backend
* Database setup
* Environment variables
* API base URL
* Authentication instructions
* API documentation
* Database schema
* Current integration status
* Known issues
* Pending work

---

# 12. Definition of Done

[ ] Authentication works
[ ] Database works
[ ] Common data models finalized
[ ] API contracts documented
[ ] APIs implemented
[ ] Validation implemented
[ ] Error handling implemented
[ ] Feature developers can integrate
[ ] Frontend can consume APIs
[ ] Backend setup documented
[ ] Integration testing completed
