# Changelog

## [Unreleased] - Blue-Green Deployment Support

### Added
- **Blue-Green Deployment Mode**: Optional dual MWAA environment setup with zero-downtime switching
  - Configure via `enable_blue_green: true` in `cdk.json`
  - Parallel deployment of Blue and Green environments (~45 minutes)
  - AWS Systems Manager Parameter Store for instant switching (< 1 second)
  - Zero-downtime DAG pattern for runtime environment detection
  
- **New Files**:
  - `stacks/mwaa_blue_green_stack.py`: Blue-Green MWAA stack implementation
  - `switch_zero_downtime.py`: CLI tool for instant environment switching
  - `assets/dags/example_blue_green_zero_downtime.py`: Zero-downtime DAG pattern
  - `BLUE_GREEN_DEPLOYMENT.md`: Complete blue-green deployment guide
  - `ZERO_DOWNTIME_GUIDE.md`: Zero-downtime switching guide
  - `DEPLOYMENT_MODES.md`: Comparison of all deployment modes
  - `QUICK_START.md`: Quick start guide for all modes
  - `cleanup_all.sh`: Cleanup script for all stacks
  - `constants.py`: Shared constants

### Changed
- **app.py**: Smart deployment logic that selects stack based on `enable_blue_green` flag
- **cdk.json**: Added `enable_blue_green` configuration flag (default: false)
- **README.md**: Updated with blue-green deployment option and comparison table
- **network_stack.py**: Added region to bucket names for global uniqueness

### Removed
- `app_ha.py`: Consolidated into main `app.py` with flag-based selection
- `README_HA_DEPLOYMENT.md`: Replaced by `DEPLOYMENT_MODES.md`
- `QUICK_ACCESS_GUIDE.md`: Replaced by `QUICK_START.md`

### Technical Details
- Blue and Green environments deploy in parallel (no dependency)
- S3 bucket names include region for global uniqueness
- Parameter Store path: `/mwaa/blue-green/active-environment`
- Both environments have SSM Parameter Store read permissions
- DAGs check parameter at runtime to determine if they should execute
- Switching updates parameter only, no MWAA environment changes

### Deployment Time
- Standard Mode: ~30 minutes (single MWAA)
- Blue-Green Mode: ~45 minutes (parallel dual MWAA)
- HA Marquez Mode: ~35 minutes (ALB + ASG + RDS)

### Breaking Changes
None - Blue-green is opt-in via configuration flag

### Migration Guide
To enable blue-green deployment:
1. Set `enable_blue_green: true` in `cdk.json`
2. Deploy: `cdk deploy --all`
3. Upload zero-downtime DAG to both environments
4. Use `switch_zero_downtime.py` to switch between environments

To disable blue-green and return to standard:
1. Set `enable_blue_green: false` in `cdk.json`
2. Destroy blue-green stack: `cdk destroy mwaa-openlineage-mwaa-bluegreen-dev`
3. Deploy standard: `cdk deploy --all`
