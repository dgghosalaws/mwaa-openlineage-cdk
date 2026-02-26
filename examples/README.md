# MWAA OpenLineage Examples

This directory contains advanced deployment examples for MWAA with OpenLineage integration.

## Available Examples

### 1. Disaster Recovery (DR)
**Directory**: `disaster-recovery/`

Deploy MWAA across two AWS regions with manual failover capabilities.

**Features**:
- Manual failover with DAG control (pause/unpause)
- DynamoDB Global Table for state management
- Sensor-based region detection (2-3 seconds)
- Cross-region S3 bucket replication for DAGs and plugins
- Cost: ~$0.43/month

**Use Case**: Production environments requiring cross-region disaster recovery with controlled failover

**Quick Start**:
```bash
cd disaster-recovery
./scripts/deploy_dr_infrastructure.sh
./scripts/init_dr_state.sh us-east-1
./scripts/deploy_phase2_with_existing_bucket.sh
```

**Documentation**: See `disaster-recovery/README.md`

---

### 2. Automated Failover
**Directory**: `automated-failover/`

Add automated health monitoring and failover to your MWAA DR setup.

**Features**:
- Continuous health monitoring (every 1 minute)
- Automatic failover after 3 consecutive failures
- Configurable health check criteria (environment status, scheduler heartbeat)
- Flapping prevention with cooldown period (30 minutes)
- Email notifications via SNS
- Cost: ~$1/month

**Use Case**: Production environments requiring automated failover without manual intervention

**Prerequisites**: Disaster Recovery example must be deployed first

**Quick Start**:
```bash
cd automated-failover
# Edit app.py to configure notification emails
cdk deploy MwaaAutomatedFailoverStack --region us-east-2
```

**Documentation**: See `automated-failover/README.md`

---

## Example Structure

Each example is self-contained with:
- `README.md` - Complete documentation
- `stacks/` - CDK stack definitions
- `assets/` - Plugins, DAGs, configurations
- `scripts/` - Deployment and operational scripts
- `docs/` - Detailed documentation

## Integration with Main Repo

Examples are designed to work with the main MWAA infrastructure:

1. **Deploy main infrastructure first** (Network, Marquez, MWAA)
2. **Deploy example on top** (adds specific capabilities)
3. **Examples are optional** (main repo works standalone)

## Prerequisites

All examples require:
- AWS CLI configured
- CDK installed and bootstrapped
- Appropriate AWS permissions
- Existing MWAA environments (or deploy new ones)

## Contributing

To add a new example:
1. Create directory: `examples/your-example/`
2. Include: README, stacks, assets, scripts, docs
3. Make it self-contained and well-documented
4. Test thoroughly before committing

## Support

For issues with examples:
1. Check example-specific documentation
2. Review troubleshooting sections
3. Check CloudWatch logs for errors

---

## Example Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                    Main MWAA Infrastructure                  │
│              (Network, Marquez, MWAA Environments)          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ├─► Disaster Recovery (Manual)
                          │   └─► Automated Failover (Optional)
                          │
                          └─► (Future examples)
```

**Deployment Order**:
1. Main infrastructure (required)
2. Disaster Recovery (optional, enables cross-region DR)
3. Automated Failover (optional, requires DR)

---

**Current Examples**: 2 (Disaster Recovery, Automated Failover)
**Status**: Production-ready
