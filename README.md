# MWAA with OpenLineage - CDK Project

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AWS CDK](https://img.shields.io/badge/AWS%20CDK-2.x-orange)](https://aws.amazon.com/cdk/)
[![Airflow](https://img.shields.io/badge/Airflow-3.0.6-blue)](https://airflow.apache.org/)
[![OpenLineage](https://img.shields.io/badge/OpenLineage-Native%20Provider-green)](https://openlineage.io/)

This CDK project creates a complete, production-ready MWAA environment with OpenLineage integration for automatic data lineage tracking using **Apache Airflow 3.0.6**.

## 🌟 Features

- ✅ **Airflow 3.0.6** with native OpenLineage provider
- ✅ **Automated deployment** with AWS CDK
- ✅ **Marquez** for lineage visualization
- ✅ **Production-ready** with security best practices
- ✅ **Comprehensive documentation** with troubleshooting guides
- ✅ **Sample DAG** demonstrating lineage capture
- ✅ **No custom plugins needed** - uses native provider

## 🚀 Quick Start

```bash
cd mwaa-openlineage-cdk
./deploy.sh
```

That's it! In 35-40 minutes you'll have a fully functional MWAA + OpenLineage environment.

## 📚 Documentation

**New to this project?** See [INDEX.md](INDEX.md) for a complete documentation guide.

- **[INDEX.md](INDEX.md)** - 📑 Documentation index and navigation guide
- **[QUICK_START.md](QUICK_START.md)** - Get started in under an hour
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Detailed architecture overview
- **[AIRFLOW_3_NOTES.md](AIRFLOW_3_NOTES.md)** - ⚠️ **IMPORTANT**: Airflow 3.0 specific configuration
- **[TESTING_GUIDE.md](TESTING_GUIDE.md)** - Comprehensive testing procedures
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Step-by-step deployment checklist
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Command reference card
- **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** - Project overview

## ⚠️ Airflow 3.0 Important Notes

This project is specifically configured for **Airflow 3.0.6** using the **native OpenLineage provider**:

1. **Uses apache-airflow-providers-openlineage** (NOT deprecated openlineage-airflow package)
2. **No custom plugins needed** - provider handles everything automatically
3. **Configuration via Airflow config options** (NOT Secrets Manager or plugins)
4. **Configuration values must be lowercase** ("false" not "False")

See [AIRFLOW_3_NOTES.md](AIRFLOW_3_NOTES.md) for complete details.

## Architecture

The project deploys three main stacks:

### 1. Network Stack
- VPC with public and private subnets across 2 AZs
- NAT Gateway for private subnet internet access
- Security groups for Marquez and MWAA
- Proper network isolation and security

### 2. Marquez Stack
- EC2 instance (t3.medium) running Marquez in Docker
- Automatic installation and configuration
- Marquez API (port 5000) and UI (port 3000)
- Systemd service for auto-restart
- SSM Session Manager enabled for secure access

### 3. MWAA Stack
- Managed Airflow 3.0.6 environment
- Native OpenLineage provider (apache-airflow-providers-openlineage)
- OpenLineage configured via Airflow configuration options
- S3 bucket with versioning for DAGs
- Sample DAG demonstrating lineage capture
- CloudWatch logging enabled

## What Gets Deployed

### Infrastructure
- ✅ VPC with public/private subnets
- ✅ Marquez server (EC2 + Docker)
- ✅ MWAA environment (mw1.small)
- ✅ S3 bucket for MWAA assets
- ✅ IAM roles and security groups

### OpenLineage Integration (Airflow 3.0)
- ✅ apache-airflow-providers-openlineage (native provider)
- ✅ Automatic HTTP transport configuration
- ✅ Configuration via Airflow config options
- ✅ No custom plugins needed
- ✅ Lowercase configuration values for Airflow 3.0

### Sample DAG
- ✅ openlineage_demo DAG
- ✅ Configuration verification
- ✅ Connectivity testing
- ✅ Sample data processing
- ✅ Lineage generation

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **AWS CDK** installed:
   ```bash
   npm install -g aws-cdk
   ```
3. **Python 3.9+** installed
4. **AWS Account** with permissions to create:
   - VPC, EC2, MWAA, S3, Secrets Manager, IAM

## Installation

### 1. Clone and Setup

```bash
# Navigate to the project directory
cd mwaa-openlineage-cdk

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Bootstrap CDK (First Time Only)

```bash
cdk bootstrap
```

### 3. Review the Stacks

```bash
# List all stacks
cdk list

# Synthesize CloudFormation templates
cdk synth

# View what will be deployed
cdk diff
```

### 4. Deploy

```bash
# Deploy all stacks
cdk deploy --all

# Or deploy individually
cdk deploy mwaa-openlineage-network-dev
cdk deploy mwaa-openlineage-marquez-dev
cdk deploy mwaa-openlineage-mwaa-dev
```

**Note**: Deployment takes approximately 30-40 minutes:
- Network Stack: ~3 minutes
- Marquez Stack: ~5 minutes (+ 2-3 minutes for Marquez to start)
- MWAA Stack: ~25-30 minutes

## Post-Deployment

### 1. Get Outputs

After deployment, note the CloudFormation outputs:

```bash
# Get all outputs
aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-mwaa-dev \
  --query 'Stacks[0].Outputs'
```

Key outputs:
- **MarquezUiUrl**: Marquez UI URL (http://...)
- **MarquezApiUrl**: Marquez API URL (http://...)
- **MwaaWebserverUrl**: Airflow UI URL (https://...)
- **MwaaBucketName**: S3 bucket name

### 2. Access Marquez UI

Open the Marquez UI URL in your browser:
```
http://<marquez-public-ip>:3000
```

### 3. Access Airflow UI

1. Go to AWS MWAA Console
2. Click on your environment: `mwaa-openlineage-dev`
3. Click "Open Airflow UI"

### 4. Verify Configuration

In MWAA Console:
1. Go to your environment: `mwaa-openlineage-dev`
2. Click "Edit"
3. Scroll to "Airflow configuration options"
4. Verify these settings exist:
   - `openlineage.transport`
   - `openlineage.namespace`
   - `openlineage.disabled`

### 5. Run the Demo DAG

1. In Airflow UI, find DAG: `openlineage_demo`
2. Enable the DAG (toggle switch)
3. Click "Trigger DAG"
4. Wait for completion (~2-3 minutes)

### 6. View Lineage in Marquez

1. Open Marquez UI
2. Select namespace: `mwaa-openlineage-dev`
3. View jobs and lineage graph
4. You should see:
   - Job: `openlineage_demo`
   - Tasks: verify_openlineage_config, test_marquez_connectivity, etc.
   - Lineage connections between tasks

## Project Structure

```
mwaa-openlineage-cdk/
├── app.py                          # CDK app entry point
├── cdk.json                        # CDK configuration
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── stacks/
│   ├── __init__.py
│   ├── network_stack.py           # VPC and networking
│   ├── marquez_stack.py           # Marquez server
│   └── mwaa_stack.py              # MWAA environment
└── assets/
    ├── dags/
    │   └── openlineage_demo_dag.py # Sample DAG
    └── requirements/
        └── requirements.txt        # Airflow requirements (native provider)
```

## Configuration

### Customize Deployment

Edit `cdk.json` to change:

```json
{
  "context": {
    "project_name": "mwaa-openlineage",  // Change project name
    "environment": "dev",                 // Change environment
    "account": "123456789012",           // Your AWS account
    "region": "us-east-1"                // Your AWS region
  }
}
```

### Customize MWAA

Edit `stacks/mwaa_stack.py`:
- Change `environment_class` (mw1.small, mw1.medium, mw1.large)
- Change `airflow_version`
- Add more Airflow configuration options
- Modify logging levels

### Customize Marquez

Edit `stacks/marquez_stack.py`:
- Change instance type
- Change Marquez version
- Add custom configuration

## Adding Your Own DAGs

### Option 1: Add to assets/dags/

1. Create your DAG file in `assets/dags/`
2. Redeploy: `cdk deploy mwaa-openlineage-mwaa-dev`

### Option 2: Upload to S3

```bash
# Get bucket name
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-mwaa-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`MwaaBucketName`].OutputValue' \
  --output text)

# Upload DAG
aws s3 cp your_dag.py s3://$BUCKET/dags/
```

## Monitoring

### Check MWAA Status

```bash
aws mwaa get-environment \
  --name mwaa-openlineage-dev \
  --query 'Environment.Status'
```

### View MWAA Logs

1. Go to MWAA Console
2. Click environment
3. Monitoring > View Logs
4. Select log type (Scheduler, Task, Webserver)

### Check Marquez Status

```bash
# Get Marquez instance ID
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-marquez-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`MarquezInstanceId`].OutputValue' \
  --output text)

# Check Docker containers
aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker ps"]'
```

### View Marquez Logs

```bash
aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker logs marquez-api --tail 100"]'
```

## Troubleshooting

### MWAA Not Starting

- Check CloudWatch logs for errors
- Verify S3 bucket has correct files
- Check IAM role permissions
- Ensure VPC has internet access (NAT Gateway)

### No Lineage Appearing

**Important**: Airflow 3.0 uses the native provider approach with automatic configuration.

1. **Check Scheduler Logs**:
   - Look for "OpenLineage provider initialized"
   - Should see transport configuration messages
   - No warnings about "REMOVED" or deprecated packages

2. **Check Configuration**:
   - MWAA Console > Environment > Airflow configuration options
   - Verify openlineage.transport, openlineage.namespace, openlineage.disabled

3. **Check Task Logs**:
   - Run a DAG and check task logs
   - Look for "Sending OpenLineage event: START"
   - Look for "Sending OpenLineage event: COMPLETE"

4. **Test Marquez**:
   ```bash
   curl http://<marquez-ip>:5000/api/v1/namespaces
   ```

5. **Common Airflow 3.0 Issues**:
   - Configuration values must be lowercase strings ("false" not "False")
   - Must use apache-airflow-providers-openlineage package
   - Old openlineage-airflow package is deprecated and will cause errors

### Marquez Not Responding

If Marquez UI is not accessible:

1. **Check if Marquez containers are running**:
   ```bash
   # Get Marquez instance ID
   INSTANCE_ID=$(aws cloudformation describe-stacks \
     --stack-name mwaa-openlineage-marquez-dev \
     --query 'Stacks[0].Outputs[?OutputKey==`MarquezInstanceId`].OutputValue' \
     --output text)
   
   # Check container status
   aws ssm send-command \
     --instance-ids "$INSTANCE_ID" \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["docker ps"]'
   ```

2. **Restart Marquez if containers are stopped**:
   ```bash
   aws ssm send-command \
     --instance-ids "$INSTANCE_ID" \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["cd /home/ec2-user/marquez && sudo -u ec2-user ./docker/up.sh --tag 0.42.0 --detach"]'
   ```

3. **Add your IP to security group** (if connection times out):
   ```bash
   # Get your IP
   MY_IP=$(curl -s https://checkip.amazonaws.com)
   
   # Get Marquez security group ID
   SG_ID=$(aws ec2 describe-security-groups \
     --filters "Name=group-name,Values=*Marquez*" \
     --query 'SecurityGroups[0].GroupId' --output text)
   
   # Add your IP for ports 3000 (UI) and 5000 (API)
   aws ec2 authorize-security-group-ingress \
     --group-id $SG_ID \
     --ip-permissions \
       IpProtocol=tcp,FromPort=3000,ToPort=3000,IpRanges="[{CidrIp=$MY_IP/32,Description='My IP for Marquez UI'}]" \
       IpProtocol=tcp,FromPort=5000,ToPort=5000,IpRanges="[{CidrIp=$MY_IP/32,Description='My IP for Marquez API'}]"
   ```

4. **Verify Marquez is responding**:
   ```bash
   # Get Marquez public IP
   MARQUEZ_IP=$(aws cloudformation describe-stacks \
     --stack-name mwaa-openlineage-marquez-dev \
     --query 'Stacks[0].Outputs[?OutputKey==`MarquezPublicIp`].OutputValue' \
     --output text)
   
   # Test API
   curl http://$MARQUEZ_IP:5000/api/v1/namespaces
   ```

**Note**: After EC2 instance reboot, Marquez containers may need to be manually restarted. The systemd service is configured to auto-start on boot, but if it fails, use the restart command above.

## Costs

Estimated monthly costs (us-east-1):

- **MWAA (mw1.small)**: ~$300/month
- **EC2 (t3.medium)**: ~$30/month
- **NAT Gateway**: ~$32/month
- **S3**: ~$1/month
- **Data Transfer**: Variable

**Total**: ~$363/month (approximate)

## Cleanup

To avoid ongoing charges, destroy all resources:

```bash
# Destroy all stacks
cdk destroy --all

# Or destroy individually (reverse order)
cdk destroy mwaa-openlineage-mwaa-dev
cdk destroy mwaa-openlineage-marquez-dev
cdk destroy mwaa-openlineage-network-dev
```

**Note**: S3 bucket will be automatically emptied and deleted.

## Security Considerations

### Production Recommendations

1. **Remove Public Access**:
   - Change Marquez to private subnet
   - Use VPN or bastion host for access
   - Set MWAA webserver to PRIVATE_ONLY

2. **Enable Encryption**:
   - Enable S3 bucket encryption with KMS
   - Enable MWAA encryption
   - Use encrypted EBS volumes

3. **Restrict Security Groups**:
   - Limit SSH access to specific IPs
   - Remove public access to Marquez UI
   - Use VPC endpoints for AWS services

4. **Enable Monitoring**:
   - Set up CloudWatch alarms
   - Enable VPC Flow Logs
   - Enable CloudTrail logging

5. **Secrets Management**:
   - Rotate Secrets Manager secrets regularly
   - Use IAM roles instead of access keys
   - Enable secret rotation

## Support

For issues or questions:
1. Check CloudWatch logs
2. Review MWAA documentation: https://docs.aws.amazon.com/mwaa/
3. Review OpenLineage docs: https://openlineage.io/docs/
4. Review Marquez docs: https://marquezproject.github.io/marquez/
5. Open an issue on GitHub: https://github.com/dgghosalaws/mwaa-openlineage-cdk/issues

## Security Testing

This project includes automated security scanning to ensure code quality and security.

### Automated Security Scans

Every push and pull request triggers:
- **Bandit**: Python security vulnerability scanner
- **Safety**: Dependency vulnerability checker
- **Checkov**: Infrastructure as Code security scanner
- **TruffleHog**: Secret detection
- **CodeQL**: Advanced code analysis
- **Dependabot**: Automated dependency updates

### Run Security Checks Locally

Before committing code, run local security checks:

```bash
# Run all security checks
./scripts/security-check.sh
```

This will scan for:
- Python security vulnerabilities
- Vulnerable dependencies
- Infrastructure security issues
- Hardcoded secrets
- Sensitive data (account IDs, IP addresses)

### Pre-commit Hooks

Install pre-commit hooks for automatic checks:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

### Security Best Practices

1. **Never commit secrets**:
   - No AWS access keys
   - No passwords
   - No API tokens

2. **Use placeholders**:
   - `YOUR-ACCOUNT-ID` instead of real account IDs
   - `YOUR-IP-ADDRESS` instead of real IPs

3. **Keep dependencies updated**:
   - Review Dependabot PRs weekly
   - Update vulnerable packages promptly

4. **Review security scan results**:
   - Check GitHub Actions for security warnings
   - Fix high-severity issues immediately

For more details, see [SECURITY.md](SECURITY.md).

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Run security checks (`./scripts/security-check.sh`)
4. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
5. Push to the branch (`git push origin feature/AmazingFeature`)
6. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- AWS MWAA team for the managed Airflow service
- OpenLineage community for the lineage standard
- Marquez team for the lineage visualization tool
- AWS CDK team for the infrastructure as code framework

## Author

**Debashis Ghosal**
- GitHub: [@dgghosalaws](https://github.com/dgghosalaws)

## Next Steps

1. ✅ Deploy the stacks
2. ✅ Verify Marquez is running
3. ✅ Run the demo DAG
4. ✅ View lineage in Marquez UI
5. 🚀 Add your own DAGs
6. 🚀 Integrate with your data pipelines
7. 🚀 Use lineage for impact analysis and compliance
