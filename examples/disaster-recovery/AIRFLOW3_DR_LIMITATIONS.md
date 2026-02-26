# Airflow 3.0 DR Limitations and Recommendations

## Critical Issue: Direct Database Access Removed

Airflow 3.0 has **completely removed** direct database access via ORM from DAGs for security reasons:

```
RuntimeError: Direct database access via the ORM is not allowed in Airflow 3.0
```

This means the original DR approach (backing up metadata tables via SQL queries) **cannot work** with Airflow 3.0.

## Impact on DR Strategy

### What We Cannot Backup via DAGs:
- ❌ DAG runs
- ❌ Task instances
- ❌ Task failures
- ❌ XCom data
- ❌ Logs
- ❌ Jobs
- ❌ Triggers
- ❌ Full connection details (passwords)

### What We CAN Backup via DAGs:
- ✅ Variables (using `Variable.get_all()`)
- ⚠️ Connections (metadata only, no passwords)
- ⚠️ Pools (limited access)

## Recommended DR Approaches for Airflow 3.0

### Option 1: RDS-Level Backup (RECOMMENDED)

Use AWS RDS automated backups or snapshots for the MWAA metadata database.

**Pros:**
- Complete metadata backup (all tables)
- Fast restore (RDS snapshot restore)
- No code changes needed
- Works with Airflow 3.0

**Cons:**
- Requires RDS access (MWAA uses managed RDS)
- Point-in-time recovery limited to RDS backup frequency

**Implementation:**
Since MWAA uses a managed RDS instance, you cannot directly access it. However, AWS MWAA automatically creates backups. For DR:

1. Use MWAA environment snapshots (via AWS Backup or manual)
2. Restore MWAA environment from snapshot in DR region
3. Update DNS/routing to point to DR environment

### Option 2: Simplified API-Based Backup (CURRENT)

Backup only critical data (Variables) using Airflow API.

**Pros:**
- Works with Airflow 3.0
- Simple implementation
- Fast backup/restore

**Cons:**
- Limited scope (only Variables)
- No DAG run history
- No task execution history

**Implementation:**
- Use `dr_backup_metadata_api.py` DAG
- Backs up Variables to S3
- Restore Variables via API in DR region

### Option 3: Downgrade to Airflow 2.x

If full metadata backup is critical, downgrade to Airflow 2.x.

**Pros:**
- Full metadata backup capability
- Original DR approach works

**Cons:**
- Missing Airflow 3.0 features
- Not future-proof
- Security concerns (why 3.0 removed DB access)

## Recommended Path Forward

### For Production DR:

**Use RDS-level backup + API-based Variable backup:**

1. **Infrastructure Level (RDS):**
   - Enable AWS Backup for MWAA environments
   - Configure cross-region backup replication
   - Test restore procedures

2. **Application Level (Variables):**
   - Use `dr_backup_metadata_api.py` for Variables
   - Store sensitive data in AWS Secrets Manager (not Variables)
   - Document manual steps for Connections/Pools

3. **Operational Level:**
   - Maintain DAG code in Git (source of truth)
   - Use Infrastructure as Code (CDK) for reproducibility
   - Document manual configuration steps

### For Testing/Development:

**Use simplified API-based backup:**
- Accept limited scope (Variables only)
- Focus on DAG code versioning
- Use IaC for environment recreation

## Migration Steps

### Immediate Actions:

1. ✅ Deploy `dr_backup_metadata_api.py` (Airflow 3.0 compatible)
2. ✅ Document limitations in DR documentation
3. ⏳ Test Variable backup/restore
4. ⏳ Evaluate AWS Backup for MWAA environments

### Long-term Actions:

1. Move sensitive data to AWS Secrets Manager
2. Implement AWS Backup for MWAA
3. Test cross-region MWAA restore
4. Update DR runbooks with new procedures

## Testing the API-Based Backup

### Deploy New DAG:

```bash
# Upload Airflow 3.0 compatible DAG
aws s3 cp mwaa-openlineage-cdk/assets/dags-dr-disabled/dr/backup_metadata_api.py \
    s3://mwaa-openlineage-mwaa-minimal-dev-us-east-1-YOUR-ACCOUNT-ID/dags/dr/

aws s3 cp mwaa-openlineage-cdk/assets/dags-dr-disabled/dr/backup_metadata_api.py \
    s3://mwaa-openlineage-mwaa-dev-us-east-2-YOUR-ACCOUNT-ID/dags/dr/
```

### Trigger and Verify:

1. Open Airflow UI
2. Find DAG: `dr_backup_metadata_api`
3. Trigger manually
4. Verify backup in S3:
   ```bash
   aws s3 ls s3://mwaa-dr-backups-us-east-2-YOUR-ACCOUNT-ID/metadata/ --recursive
   ```

### Expected Backup Contents:

```
metadata/20260226_090000/
├── variables.json          # All Airflow Variables
├── connections.json        # Connection metadata (no passwords)
├── pools.json             # Pool metadata
└── manifest.json          # Backup metadata
```

## Conclusion

Airflow 3.0's removal of direct database access is a **breaking change** for traditional DR approaches. The recommended solution is:

1. **Primary:** Use AWS-level backup (RDS snapshots, MWAA environment backups)
2. **Secondary:** Use API-based Variable backup for quick recovery
3. **Tertiary:** Maintain DAG code in Git and use IaC for environment recreation

This provides a more robust, cloud-native DR strategy that aligns with Airflow 3.0's architecture.
