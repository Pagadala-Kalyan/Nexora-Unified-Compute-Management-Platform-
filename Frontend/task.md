# NEXORA — FRONTEND TASK

## 1. Role

You are responsible for the complete frontend/interface of Nexora.

Your job is to create the user-facing interface and integrate it with the APIs provided by the backend.

You are NOT responsible for implementing backend business logic.

---

# 2. Phase 1 Features to Represent

The frontend must provide interfaces for:

1. Remote Execution
2. Failure Detection & Checkpointing Recovery
3. Billing & Wallet
4. Resource Pool

---

# 3. Preparation

Before coding:

* Understand the complete Nexora project idea.
* Understand all four Phase 1 features.
* Study the backend API requirements.
* Understand the data that each API will return.
* Decide the frontend technology.
* Create a basic UI flow.
* Create wireframes before implementing major screens.

---

# 4. Required Screens

Create interfaces for at least:

### Authentication

* Login
* Registration

### Dashboard

* Overall system status
* Running jobs
* Available resources
* Wallet balance
* Recent activity

### Remote Execution

* Submit job
* Select/describe workload requirements
* Job status
* Running job information
* Job output/result
* Job history

### Resource Pool

* Available resources
* CPU/GPU information
* RAM/storage
* Resource status
* Resource utilization
* Selected/allocated resource

### Failure Recovery

* Job failure notification
* Failure reason/status
* Last checkpoint
* Recovery status
* Resume status
* Job migration/recovery information

### Billing & Wallet

* Wallet balance
* Add credits
* Usage cost
* Current job cost
* Transaction history
* Billing history

---

# 5. API Integration

Do NOT hardcode final data.

The frontend must consume backend APIs.

For every API, document:

* API endpoint
* HTTP method
* Request format
* Response format
* Authentication requirement
* Error response
* Loading state
* Empty state

Create an API integration file/document such as:

`API_MAPPING.md`

Example:

| Feature      | API                  | Method | Frontend Use          |
| ------------ | -------------------- | ------ | --------------------- |
| Submit Job   | /jobs                | POST   | Submit workload       |
| Job Status   | /jobs/{id}           | GET    | Display status        |
| Resources    | /resources           | GET    | Display resource pool |
| Wallet       | /wallet              | GET    | Display balance       |
| Transactions | /wallet/transactions | GET    | Display history       |

The actual endpoints must be finalized collaboratively with the backend developer.

---

# 6. Collaboration With Backend

You MUST coordinate with Person 2 before finalizing API integration.

Agree on:

* Endpoint names
* Request JSON
* Response JSON
* Error format
* Authentication
* Job status values
* Resource status values
* Billing fields
* Recovery status fields

Do not independently invent API structures.

---

# 7. Collaboration With Feature Developers

### With Person 3

Need information about:

* Job submission fields
* Job status
* Resource information
* Resource utilization
* Execution result
* Resource allocation

### With Person 4

Need information about:

* Failure status
* Checkpoint information
* Recovery status
* Wallet information
* Billing information
* Transaction information

---

# 8. Frontend Deliverables

You must provide:

* UI wireframes
* Screen designs
* Frontend project
* Reusable components
* API integration
* Loading/error states
* Responsive interface
* Final integrated frontend

---

# 9. Integration Requirements

Before declaring frontend complete:

* Replace dummy API data with backend APIs.
* Test every API integration.
* Test failed API requests.
* Test empty data.
* Test loading states.
* Verify authentication.
* Verify job status updates.
* Verify wallet updates.
* Verify resource updates.
* Verify failure/recovery information.

---

# 10. Handover

Maintain:

`FRONTEND_HANDOVER.md`

It must contain:

* Frontend technology
* How to run frontend
* Folder structure
* Environment variables
* API base URL
* Required dependencies
* List of completed screens
* API integration status
* Known issues
* Pending integration work

---

# 11. Definition of Done

Frontend is complete only when:

[ ] All Phase 1 screens exist
[ ] UI is connected to backend
[ ] Authentication works
[ ] Job submission works
[ ] Job status is displayed
[ ] Resources are displayed
[ ] Failure/recovery status is displayed
[ ] Wallet is displayed
[ ] Billing history is displayed
[ ] Error handling exists
[ ] Loading states exist
[ ] Final integration is tested
