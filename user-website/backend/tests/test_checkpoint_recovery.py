"""
Automated test suite proving genuine execution checkpointing, integrity verification,
fencing token enforcement, and cooperative recovery in Nexora UCMP.
"""
import os
import sys
import json
import hashlib
import tempfile
import pytest

# Point to isolated temporary database before importing app
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"

# Ensure provider-server and backend are on sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_backend_path = os.path.join(_repo_root, "user-website", "backend")
_provider_path = os.path.join(_repo_root, "provider-server")

for p in [_backend_path, _provider_path]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from app.main import Base, app, engine, Job, Checkpoint, Provider, User, JobBilling, wallet_for, token_ledger
from sqlalchemy.orm import sessionmaker

Base.metadata.create_all(engine)
client = TestClient(app)
SessionLocal = sessionmaker(bind=engine)

# Import provider functions
import main as provider_main


def compute_canonical_hash(data: dict) -> str:
    serialized = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def seed_test_user_and_provider(db, user_id=1, provider_id="prov_test_1"):
    u = db.get(User, user_id)
    if not u:
        u = User(id=user_id, email=f"user_{user_id}@example.test", password_hash="dummy_hash", wallet_balance=100.0)
        db.merge(u)
    p = db.get(Provider, provider_id)
    if not p:
        p = Provider(
            id=provider_id,
            name=f"Provider {provider_id}",
            cpu_cores=8,
            ram_gb=16.0,
            gpu_name="NVIDIA RTX 4090",
            gpu_memory_gb=24.0,
            status="ONLINE",
            utilization={}
        )
        db.merge(p)
    db.commit()
    return u, p


# ============================================================
# STAGE 3 & 7: WORKLOAD STATE MATHEMATICAL CORRECTNESS
# ============================================================

class TestWorkloadCheckpointRecovery:

    def test_prime_search_recovery_mathematical_identity(self):
        """
        Proves prime search saves real algorithm state and resumes without
        re-computing previous slices or producing duplicates/omissions.
        """
        limit = 1200

        # 1. Run uninterrupted execution
        uninterrupted_reports = []
        uninterrupted_res = provider_main.run_prime_search(
            limit=limit,
            report=lambda p, s: uninterrupted_reports.append((p, s))
        )
        assert len(uninterrupted_reports) == 4
        assert uninterrupted_res["prime_count"] == len(uninterrupted_res["primes"])

        # 2. Simulate worker crash after slice 1 (25% progress)
        slice_1_checkpoint = uninterrupted_reports[0][1]
        assert slice_1_checkpoint["completed_slices"] == 1
        primes_at_checkpoint = list(slice_1_checkpoint["accumulated_primes"])
        assert len(primes_at_checkpoint) > 0

        # 3. Fresh worker resumes using only the checkpoint state
        resumed_reports = []
        resumed_res = provider_main.run_prime_search(
            limit=limit,
            report=lambda p, s: resumed_reports.append((p, s)),
            resume_state=slice_1_checkpoint
        )

        # 4. Verify completed work was skipped (only 3 slices computed: 50%, 75%, 100%)
        assert len(resumed_reports) == 3
        assert [p for p, _ in resumed_reports] == [50, 75, 100]

        # 5. Verify mathematical identity against uninterrupted execution
        assert resumed_res["prime_count"] == uninterrupted_res["prime_count"]
        assert resumed_res["last_prime"] == uninterrupted_res["last_prime"]
        assert resumed_res["primes"] == uninterrupted_res["primes"]
        assert len(resumed_res["primes"]) == len(set(resumed_res["primes"])), "No duplicate primes allowed"

    def test_fibonacci_recovery_mathematical_identity(self):
        """
        Proves Fibonacci saves exact big-integer sequence state and resumes
        computing from the saved milestone without starting over.
        """
        index = 80

        # 1. Uninterrupted
        uninterrupted_reports = []
        uninterrupted_res = provider_main.run_fibonacci(
            index=index,
            report=lambda p, s: uninterrupted_reports.append((p, s))
        )
        assert len(uninterrupted_reports) == 4

        # 2. Simulate crash after slice 2 (50% progress)
        slice_2_checkpoint = uninterrupted_reports[1][1]
        assert slice_2_checkpoint["completed_slices"] == 2
        assert slice_2_checkpoint["completed_index"] == (2 * index) // 4

        # 3. Fresh worker resumes from checkpoint state
        resumed_reports = []
        resumed_res = provider_main.run_fibonacci(
            index=index,
            report=lambda p, s: resumed_reports.append((p, s)),
            resume_state=slice_2_checkpoint
        )

        # 4. Verify work was skipped (only parts 3 and 4 computed)
        assert len(resumed_reports) == 2
        assert [p for p, _ in resumed_reports] == [75, 100]

        # 5. Verify mathematical identity
        assert resumed_res["value"] == uninterrupted_res["value"]
        assert resumed_res["digits"] == uninterrupted_res["digits"]

    def test_matrix_multiply_recovery_mathematical_identity(self):
        """
        Proves matrix multiplication saves tile checksums and resumes
        computation only for unfinished tiles, matching uninterrupted result.
        """
        size = 64

        # 1. Uninterrupted
        uninterrupted_reports = []
        uninterrupted_res = provider_main.run_matrix_multiply(
            size=size,
            report=lambda p, s: uninterrupted_reports.append((p, s))
        )
        assert len(uninterrupted_reports) == 4

        # 2. Simulate crash after tile 1 (25% progress)
        tile_1_checkpoint = uninterrupted_reports[0][1]
        assert tile_1_checkpoint["completed_tiles"] == 1
        assert len(tile_1_checkpoint["tile_checksums"]) == 1

        # 3. Fresh worker resumes from checkpoint state
        resumed_reports = []
        resumed_res = provider_main.run_matrix_multiply(
            size=size,
            report=lambda p, s: resumed_reports.append((p, s)),
            resume_state=tile_1_checkpoint
        )

        # 4. Verify remaining 3 tiles computed
        assert len(resumed_reports) == 3
        assert [p for p, _ in resumed_reports] == [50, 75, 100]

        # 5. Verify mathematical checksum identity
        assert resumed_res["checksum"] == uninterrupted_res["checksum"]


# ============================================================
# STAGE 4 & 7: DURABLE STORAGE, INTEGRITY & CORRUPTION FALLBACK
# ============================================================

class TestCheckpointIntegrityAndFallback:

    def test_integrity_hash_verification_on_commit(self):
        """Verifies control plane enforces SHA-256 integrity hash on checkpoint commits."""
        headers = {"X-Provider-Token": "local-demo-token"}
        
        db = SessionLocal()
        seed_test_user_and_provider(db, user_id=10, provider_id="prov_test_int")
        j = Job(id="job_test_int", user_id=10, provider_id="prov_test_int", name="Integrity Job", workload="prime_search", status="RUNNING", requirements={}, attempt=1)
        db.merge(j)
        db.commit()
        db.close()

        valid_state = {"workload": "prime_search", "limit": 100, "completed_slices": 1, "accumulated_primes": [2, 3, 5]}
        valid_hash = compute_canonical_hash(valid_state)

        # Commit with correct hash -> 200 OK
        res = client.post(
            "/providers/jobs/job_test_int/checkpoint",
            headers=headers,
            json={
                "progress": 25,
                "attempt": 1,
                "seq": 1,
                "state_hash": valid_hash,
                "state": valid_state
            }
        )
        assert res.status_code == 200
        assert res.json()["state_hash"] == valid_hash

        # Commit with tampered hash -> 422 Unprocessable Entity
        res_bad = client.post(
            "/providers/jobs/job_test_int/checkpoint",
            headers=headers,
            json={
                "progress": 50,
                "attempt": 1,
                "seq": 2,
                "state_hash": "deadbeef00000000000000000000000000000000000000000000000000000000",
                "state": valid_state
            }
        )
        assert res_bad.status_code == 422

    def test_safe_fallback_on_corrupted_newest_checkpoint(self, monkeypatch):
        """
        Simulates storage-level corruption of newest checkpoint (seq=2)
        and confirms provider safely falls back to earlier valid checkpoint (seq=1).
        """
        job_id = "job_test_fallback"
        db = SessionLocal()
        seed_test_user_and_provider(db, user_id=11, provider_id="prov_fallback")
        j = Job(id=job_id, user_id=11, name="Fallback Job", workload="prime_search", status="RECOVERING", requirements={}, attempt=2)
        db.merge(j)

        # Checkpoint 1: Valid
        cp1_payload = {"workload": "prime_search", "limit": 500, "completed_slices": 1, "accumulated_primes": [2, 3, 5, 7]}
        cp1_hash = compute_canonical_hash(cp1_payload)
        cp1 = Checkpoint(id="cp_valid_1", job_id=job_id, provider_id="prov_fallback", attempt=1, seq=1, progress=25, state_hash=cp1_hash, payload=cp1_payload)
        db.merge(cp1)

        # Checkpoint 2: Corrupted on disk (payload was tampered with after hash was saved)
        cp2_tampered_payload = {"workload": "prime_search", "limit": 500, "completed_slices": 2, "accumulated_primes": [999999]}
        cp2 = Checkpoint(id="cp_corrupt_2", job_id=job_id, provider_id="prov_fallback", attempt=1, seq=2, progress=50, state_hash="orig_hash_prior_to_corruption", payload=cp2_tampered_payload)
        db.merge(cp2)
        db.commit()
        db.close()

        # Route provider HTTP requests to TestClient
        def mock_request(method, path, **kwargs):
            if method == "GET":
                return client.get(path, headers={"X-Provider-Token": "local-demo-token"})
            return client.post(path, headers={"X-Provider-Token": "local-demo-token"}, **kwargs)

        monkeypatch.setattr(provider_main, "request", mock_request)

        # Call provider's fetch_valid_checkpoint
        chosen_cp = provider_main.fetch_valid_checkpoint(job_id)
        assert chosen_cp is not None
        assert chosen_cp["id"] == "cp_valid_1", "Must fall back to valid checkpoint seq 1"
        assert chosen_cp["seq"] == 1


# ============================================================
# STAGE 5 & 7: FENCING TOKENS & CONCURRENCY SAFEGUARDS
# ============================================================

class TestFencingAndConcurrency:

    def test_stale_provider_rejected_by_fencing_token(self):
        """
        Proves that an old execution attempt (Provider A, attempt 1) is rejected
        with HTTP 409 Conflict when a replacement provider has taken over (attempt 2).
        """
        headers = {"X-Provider-Token": "local-demo-token"}
        job_id = "job_test_fencing"

        db = SessionLocal()
        seed_test_user_and_provider(db, user_id=12, provider_id="prov_fencing")
        j = Job(id=job_id, user_id=12, name="Fenced Job", workload="prime_search", status="RUNNING", requirements={}, attempt=1)
        db.merge(j)
        db.commit()
        db.close()

        # Provider A (attempt 1) updates successfully
        res = client.post(f"/providers/jobs/{job_id}/update", headers=headers, json={"progress": 25, "attempt": 1})
        assert res.status_code == 200

        # Control plane recovers job -> attempt incremented to 2
        db = SessionLocal()
        j = db.get(Job, job_id)
        j.attempt = 2
        j.status = "RECOVERING"
        db.commit()
        db.close()

        # Stale Provider A sends late update with attempt 1 -> MUST BE REJECTED with 409
        stale_update = client.post(f"/providers/jobs/{job_id}/update", headers=headers, json={"progress": 50, "attempt": 1})
        assert stale_update.status_code == 409
        assert "Stale execution attempt rejected" in stale_update.json()["detail"]["message"]

        # Stale Provider A sends late checkpoint with attempt 1 -> MUST BE REJECTED with 409
        stale_cp = client.post(
            f"/providers/jobs/{job_id}/checkpoint",
            headers=headers,
            json={
                "progress": 50,
                "attempt": 1,
                "seq": 2,
                "state": {"data": "stale"}
            }
        )
        assert stale_cp.status_code == 409
        assert "Stale checkpoint rejected" in stale_cp.json()["detail"]["message"]

        # Replacement Provider B sends update with attempt 2 -> Accepted
        valid_update = client.post(f"/providers/jobs/{job_id}/update", headers=headers, json={"progress": 50, "attempt": 2})
        assert valid_update.status_code == 200


# ============================================================
# STAGE 5 & 7: BILLING IDEMPOTENCY THROUGH RECOVERY
# ============================================================

class TestBillingIdempotency:

    def test_billing_settled_exactly_once_after_recovery(self):
        """
        Verifies that tokens reserved for a job are settled exactly once,
        even if retried, recovered across providers, or subjected to duplicate completion calls.
        """
        headers = {"X-Provider-Token": "local-demo-token"}
        job_id = "job_test_billing"
        user_id = 13

        db = SessionLocal()
        seed_test_user_and_provider(db, user_id=user_id, provider_id="prov_billing")
        # Setup user wallet with 1000 tokens
        w = wallet_for(db, user_id)
        w.token_balance = 1000
        # Reserve 50 tokens for job
        w.token_balance -= 50
        bill = JobBilling(job_id=job_id, estimated_tokens=50, reserved_tokens=50, actual_tokens=0)
        db.merge(bill)
        j = Job(id=job_id, user_id=user_id, provider_id="prov_billing", name="Billing Job", workload="fibonacci", status="RUNNING", requirements={}, attempt=2)
        db.merge(j)
        db.commit()
        db.close()

        # Job completed on attempt 2 (elapsed_seconds = 2.0 -> actual tokens = 4)
        comp_res = client.post(
            f"/providers/jobs/{job_id}/update",
            headers=headers,
            json={
                "status": "COMPLETED",
                "progress": 100,
                "attempt": 2,
                "result": {"elapsed_seconds": 2.0}
            }
        )
        assert comp_res.status_code == 200

        # Verify wallet balance: 1000 - 4 = 996
        db = SessionLocal()
        w = wallet_for(db, user_id)
        assert w.token_balance == 996
        bill = db.get(JobBilling, job_id)
        assert bill.reserved_tokens == 0
        assert bill.actual_tokens == 4
        db.close()

        # Duplicate completion call from stale attempt 1 -> Rejected
        dup_stale = client.post(
            f"/providers/jobs/{job_id}/update",
            headers=headers,
            json={
                "status": "COMPLETED",
                "progress": 100,
                "attempt": 1,
                "result": {"elapsed_seconds": 10.0}
            }
        )
        assert dup_stale.status_code == 409

        # Duplicate completion call from attempt 2 -> Handled idempotently (no double deduction)
        dup_attempt2 = client.post(
            f"/providers/jobs/{job_id}/update",
            headers=headers,
            json={
                "status": "COMPLETED",
                "progress": 100,
                "attempt": 2,
                "result": {"elapsed_seconds": 2.0}
            }
        )
        assert dup_attempt2.status_code == 200

        # Balance must remain exactly 996
        db = SessionLocal()
        w = wallet_for(db, user_id)
        assert w.token_balance == 996
        db.close()


# ============================================================
# STAGE 7: TWO-PROVIDER END-TO-END EXECUTION & RECOVERY
# ============================================================

class TestTwoProviderIntegration:

    def test_two_provider_handoff_and_completion(self, monkeypatch):
        """
        End-to-end integration test:
        1. Provider A executes real prime_search work and checkpoints at 25% and 50%.
        2. Provider A is abruptly terminated.
        3. Control plane triggers recovery (increments attempt to 2, marks RECOVERING).
        4. Provider B retrieves the job, loads the durable checkpoint, and resumes.
        5. Work finishes at 100% and matches uninterrupted output.
        """
        job_id = "job_test_e2e_two_prov"
        limit = 1000

        # Register providers A & B
        db = SessionLocal()
        seed_test_user_and_provider(db, user_id=14, provider_id="prov_A")
        seed_test_user_and_provider(db, user_id=14, provider_id="prov_B")
        
        bill = JobBilling(job_id=job_id, estimated_tokens=50, reserved_tokens=50, actual_tokens=0)
        db.merge(bill)
        j = Job(id=job_id, user_id=14, name="E2E Recovery Job", workload="prime_search", status="SCHEDULED", requirements={"matrix_size": limit}, provider_id="prov_A", attempt=1)
        db.merge(j)
        db.commit()
        db.close()

        def mock_request(method, path, **kwargs):
            if method == "GET":
                return client.get(path, headers={"X-Provider-Token": "local-demo-token"})
            return client.post(path, headers={"X-Provider-Token": "local-demo-token"}, **kwargs)

        monkeypatch.setattr(provider_main, "request", mock_request)

        # Provider A executes partially: writes 2 checkpoints (25% and 50%), then crashes
        checkpoints_written = []
        def prov_a_report(progress, state):
            res = client.post(
                f"/providers/jobs/{job_id}/checkpoint",
                headers={"X-Provider-Token": "local-demo-token"},
                json={
                    "progress": progress,
                    "attempt": 1,
                    "seq": len(checkpoints_written) + 1,
                    "state_hash": compute_canonical_hash(state),
                    "state": state
                }
            )
            assert res.status_code == 200
            checkpoints_written.append((progress, state))
            if progress >= 50:
                raise KeyboardInterrupt("Simulated Provider A crash!")

        try:
            provider_main.run_prime_search(limit=limit, report=prov_a_report)
        except KeyboardInterrupt:
            pass  # Provider A terminated

        assert len(checkpoints_written) == 2
        assert checkpoints_written[-1][0] == 50

        # Control plane detects provider loss and recovers job
        db = SessionLocal()
        j = db.get(Job, job_id)
        j.status = "RECOVERING"
        j.attempt = 2
        j.recovery_count = 1
        j.provider_id = "prov_B"
        db.commit()
        db.close()

        # Provider B receives recovered job
        job_for_b = {
            "id": job_id,
            "workload": "prime_search",
            "status": "RECOVERING",
            "attempt": 2,
            "recovery_count": 1,
            "requirements": {"matrix_size": limit}
        }

        # Set provider identity to prov_B
        monkeypatch.setattr(provider_main, "PID", "prov_B")

        # Provider B executes job to completion
        provider_main.execute(job_for_b)

        # Verify final state on control plane
        db = SessionLocal()
        final_job = db.get(Job, job_id)
        assert final_job.status == "COMPLETED"
        assert final_job.progress == 100
        assert final_job.attempt == 2
        assert final_job.recovery_count == 1
        assert final_job.result["recovered"] is True

        # Verify final primes result matches an uninterrupted run
        uninterrupted = provider_main.run_prime_search(limit=limit, report=lambda p, s: None)
        assert final_job.result["output"]["prime_count"] == uninterrupted["prime_count"]
        assert final_job.result["output"]["primes"] == uninterrupted["primes"]
        db.close()
