# NEXORA — REMOTE EXECUTION + RESOURCE POOL TASK

## 1. Role

You are responsible for the compute/resource side of Nexora.

Your two main features are:

1. Remote Execution
2. Resource Pool

Your goal is to make Nexora capable of identifying available compute resources and executing a submitted workload on an appropriate resource.

---

# 2. Preparation

Before coding:

* Understand Nexora's UCMP concept.
* Study remote execution concepts.
* Study CPU/GPU resource management.
* Understand how jobs are represented.
* Understand the backend API contract.
* Understand the failure recovery requirements from Person 4.

---

# 3. RESOURCE POOL

Implement:

### Resource Registration

A resource should contain information such as:

* Resource ID
* Name
* Provider/type
* CPU
* GPU
* RAM
* Storage
* Operating system
* Location/type if required
* Status
* Utilization
* Availability

---

### Resource States

Define common states such as:

* AVAILABLE
* BUSY
* OFFLINE
* FAILED
* MAINTENANCE

Finalize these states with the backend developer.

---

### Resource Monitoring

Track:

* CPU utilization
* GPU utilization
* Memory utilization
* Resource availability
* Running job
* Health/status

For the student prototype, simulated resources may be used where real cloud infrastructure is unavailable.

---

### Resource Allocation

When a job needs compute:

1. Receive job requirements.
2. Check available resources.
3. Find suitable resources.
4. Select a resource.
5. Mark resource as allocated.
6. Execute the job.
7. Release resource after completion.

---

# 4. REMOTE EXECUTION

Implement the execution pipeline:

```text
User submits job
       ↓
Backend receives job
       ↓
Requirements identified
       ↓
Resource selected
       ↓
Job sent to resource
       ↓
Execution starts
       ↓
Monitor execution
       ↓
Collect output
       ↓
Update job status
       ↓
Release resource
```

---

# 5. Execution Requirements

The prototype should demonstrate:

* Job submission
* Resource selection
* Remote/local worker execution
* Process execution
* Execution status
* Output collection
* Job completion
* Job failure

Where real remote machines are unavailable, use a controlled worker/simulated resource architecture.

---

# 6. Job States

Work with the team to finalize states such as:

```text
QUEUED
ALLOCATING
RUNNING
COMPLETED
FAILED
RECOVERING
CANCELLED
```

Do NOT create conflicting status names.

---

# 7. Collaboration With Person 2

Agree on:

* Job schema
* Resource schema
* Job APIs
* Resource APIs
* Execution status
* Resource status

Person 2 provides the backend infrastructure.

You provide the compute/resource logic.

---

# 8. Collaboration With Person 4

This is critical.

Person 4 needs execution information for failure recovery.

Provide:

* Job ID
* Current execution state
* Assigned resource
* Execution progress
* Checkpoint trigger information
* Failure event
* Last known execution state

When a resource fails, your module should allow the recovery module to know:

> Which job was running, where it was running, and what happened.

---

# 9. Collaboration With Person 1

Provide the frontend developer with:

* Job submission fields
* Job status fields
* Resource information
* Resource utilization information
* Execution result format

---

# 10. Testing

Test:

* Resource registration
* Resource availability
* Resource allocation
* Resource release
* Successful execution
* Failed execution
* Multiple resources
* Resource unavailable
* Invalid job
* Worker failure

---

# 11. Handover

Maintain:

`COMPUTE_HANDOVER.md`

Include:

* How resource pool works
* Resource data structure
* Execution architecture
* Worker setup
* How to run execution
* APIs used
* APIs provided
* Job states
* Resource states
* Failure events
* Integration instructions
* Known issues

---

# 12. Definition of Done

[ ] Resources can be registered
[ ] Resources have status
[ ] Resources can be allocated
[ ] Resources can be released
[ ] Jobs can be executed
[ ] Execution status is available
[ ] Output can be collected
[ ] Failed execution can be identified
[ ] Recovery module can receive failure information
[ ] Backend integration works
[ ] Frontend integration works
[ ] Demo scenario works
