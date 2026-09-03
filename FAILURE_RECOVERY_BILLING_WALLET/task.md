# NEXORA — FAILURE RECOVERY + BILLING & WALLET TASK

## 1. Role

You are responsible for two major Nexora features:

1. Failure Detection & Checkpointing Recovery
2. Billing & Wallet

These features provide reliability and financial management for Nexora.

---

# 2. PREPARATION

Before coding:

* Understand the complete Nexora architecture.
* Study failure detection.
* Study checkpointing.
* Study recovery/resume mechanisms.
* Study resource failure scenarios.
* Design the wallet model.
* Design the pricing model.
* Understand compute usage measurement.

---

# 3. FAILURE DETECTION

Detect situations such as:

* Worker failure
* Resource becoming unavailable
* Process crash
* Connection loss
* Job timeout
* Unexpected termination

Create a failure event containing:

* Job ID
* Resource ID
* Failure type
* Failure time
* Last known state
* Last checkpoint
* Recovery status

---

# 4. CHECKPOINTING

The system should periodically save job progress.

A checkpoint should contain appropriate information such as:

* Checkpoint ID
* Job ID
* Resource ID
* Timestamp
* Progress/state
* Required recovery data
* Storage location

The checkpoint frequency should be configurable.

For the student prototype, checkpointing may use a simplified but demonstrable mechanism rather than implementing a production-grade distributed checkpoint system.

---

# 5. RECOVERY

Basic recovery flow:

```text
Job Running
    ↓
Checkpoint Created
    ↓
Resource Failure
    ↓
Failure Detected
    ↓
Find Last Checkpoint
    ↓
Find Available Resource
    ↓
Restore Checkpoint
    ↓
Resume Job
    ↓
Continue Execution
```

The demo must clearly show that the job does not simply restart from zero.

---

# 6. BILLING & WALLET

Implement:

### Wallet

* User wallet
* Current balance
* Add credits
* Deduct credits
* Transaction history

For the prototype, use simulated credits/money.

No real payment gateway is required for Phase 1.

---

# 7. PRICING MODEL

Define a simple transparent pricing model.

For example:

```text
Cost = Resource Usage × Resource Rate
```

Possible usage metrics:

* CPU time
* GPU time
* RAM usage
* Storage
* Execution duration

Keep the initial model simple enough to demonstrate clearly.

The final pricing formula must be documented.

---

# 8. BILLING FLOW

```text
Job Submitted
      ↓
Resource Allocated
      ↓
Job Executes
      ↓
Usage Recorded
      ↓
Cost Calculated
      ↓
Wallet Checked
      ↓
Amount Deducted
      ↓
Transaction Created
      ↓
Billing History Updated
```

---

# 9. Wallet Safety

Handle:

* Insufficient balance
* Invalid transaction
* Duplicate transaction
* Failed deduction
* Job cancellation
* Failed job

The team must decide how failed/recovered jobs are charged.

Document the decision.

---

# 10. Collaboration With Person 2

Agree on:

* Wallet schema
* Transaction schema
* Billing schema
* Failure schema
* Checkpoint schema
* API contracts

Person 2 provides backend infrastructure.

You provide the business logic.

---

# 11. Collaboration With Person 3

This integration is critical.

Person 3 provides:

* Job execution duration
* Resource ID
* Resource type
* CPU/GPU usage
* Job completion/failure
* Resource changes

You use this information to:

* Calculate cost
* Record usage
* Create billing transactions
* Trigger recovery logic where required

---

# 12. Collaboration With Person 1

Provide frontend requirements for:

### Recovery

* Failure status
* Failure reason
* Checkpoint status
* Recovery status
* Resume status

### Billing

* Wallet balance
* Job cost
* Usage
* Transactions
* Billing history

---

# 13. Testing

Test:

### Recovery

* Successful checkpoint
* Resource failure
* Failure detection
* Checkpoint retrieval
* Resource replacement
* Resume from checkpoint
* Recovery failure

### Billing

* Successful payment/credit
* Wallet deduction
* Insufficient balance
* Job completion billing
* Failed job billing
* Transaction history
* Duplicate transaction

---

# 14. Handover

Maintain:

`RELIABILITY_FINANCE_HANDOVER.md`

Include:

* Failure detection design
* Checkpoint design
* Recovery workflow
* Failure states
* Billing formula
* Pricing model
* Wallet schema
* Transaction schema
* APIs required
* APIs provided
* Integration instructions
* Known issues

---

# 15. Definition of Done

[ ] Failures can be detected
[ ] Checkpoints can be created
[ ] Checkpoints can be retrieved
[ ] Failed jobs can recover
[ ] Recovery can resume execution
[ ] Wallet works
[ ] Credits can be added
[ ] Usage can be calculated
[ ] Job cost can be calculated
[ ] Transactions are recorded
[ ] Insufficient balance is handled
[ ] Backend integration works
[ ] Frontend integration works
[ ] Complete failure + recovery + billing demo works
