# MWAA DR Example - Deployment Success

## Deployment Summary

Successfully deployed a complete MWAA Disaster Recovery setup across two AWS regions with the following architecture:

### Infrastructure Deployed

**Primary Region (us-east-2):**
- VPC with public/private subnets and NAT gateway
- S3 bucket with versioning (S3-managed encryption)
- MWAA environment (mwaa-openlineage-dr-primary-dev)
- DR plugin, test DAG, and requirements uploaded

**Secondary Region (us-east-1):**
- VPC with public/private subnets and NAT gateway
- S3 bucket with versioning (S3-managed encryption)
- MWAA environment (mwaa-openlineage-dr-secondary-dev)
- DR plugin, test DAG, and requirements uploaded

**Shared Resources:**
- DynamoDB table (mwaa-openlineage-dr-state-dev) in us-east-2
- Active region set to: us-east-2

### Key Design Decisions

1. **Simplified Encryption**: Using S3-managed encryption instead of custom KMS keys
   - Reduces complexity and cost
   - MWAA uses its own AWS-managed encryption
   - No KMS VPC endpoint needed

2. **Correct Deployment Order**: 
   - Create S3 bucket first
   - Upload plugin (zipped), DAGs, and requirements to S3
   - Then create MWAA environment referencing pre-uploaded assets
   - This avoids the "INCORRECT_CONFIGURATION" errors

3. **Plugin Deployment**: Plugin is zipped and uploaded to `plugins/plugins.zip` path

### Verification

Both MWAA environments are AVAILABLE with DR configuration:
```json
{
    "dr.enabled": "true",
    "dr.state_source": "dynamodb",
    "dr.state_table": "mwaa-openlineage-dr-state-dev",
    "dr.state_table_region": "us-east-2"
}
```

### Next Steps

1. **Verify DR Plugin is Working:**
   ```bash
   # Check scheduler logs in both regions
   # Look for "DR state checking ENABLED" message
   ```

2. **Test Failover:**
   ```bash
   # Switch active region to secondary
   aws dynamodb put-item \
     --table-name mwaa-openlineage-dr-state-dev \
     --region us-east-2 \
     --item '{"state_id": {"S": "ACTIVE_REGION"}, "value": {"S": "us-east-1"}, "last_updated": {"N": "'$(date +%s)'"}}'
   ```

3. **Monitor DAG Execution:**
   - Primary region: DAGs should run when active
   - Secondary region: DAGs should be skipped when inactive

### Cleanup

To delete all resources:
```bash
./cleanup_complete.sh
```

## Deployment Time

- Network stacks: ~2-3 minutes each
- S3 stacks: ~1 minute each
- Asset uploads: <1 minute each
- MWAA environments: ~20-25 minutes each
- **Total: ~45-50 minutes**

## Cost Optimization

- Using mw1.small environment class (minimal cost)
- 1-2 workers per environment
- S3-managed encryption (no KMS key costs)
- No unnecessary VPC endpoints

## Files Created/Modified

### New Files:
- `stacks/dr_s3_stack.py` - S3 bucket stack
- `stacks/dr_network_stack.py` - Simplified network stack
- `stacks/dr_mwaa_stack.py` - MWAA stack (imports S3 bucket)
- `scripts/upload_assets.sh` - Asset upload script
- `deploy_complete.sh` - Complete deployment script
- `cleanup_complete.sh` - Cleanup script

### Key Changes:
- Removed custom KMS encryption (using S3-managed)
- Removed KMS VPC endpoint (not needed)
- S3 bucket created separately from MWAA stack
- Assets uploaded before MWAA creation
- MWAA references `plugins_s3_path="plugins/plugins.zip"`

## Lessons Learned

1. MWAA requires assets to be in S3 before environment creation
2. Custom KMS encryption adds unnecessary complexity for this use case
3. S3-managed encryption is sufficient and simpler
4. Plugin must be zipped before upload
5. Proper deployment order is critical for success
