# Documentation Index

Complete guide to all documentation in this repository.

## 📚 Main Documentation

### Getting Started
- **[README.md](README.md)** - Main entry point, quick start for all four deployment modes
- **[QUICK_START.md](QUICK_START.md)** - Step-by-step deployment guide
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design decisions

### Deployment Modes
- **[DEPLOYMENT_MODES.md](DEPLOYMENT_MODES.md)** - Comparison of all four deployment modes
- **[BLUE_GREEN_DEPLOYMENT.md](BLUE_GREEN_DEPLOYMENT.md)** - Blue-Green MWAA deployment guide
- **[FULL_HA_GUIDE.md](FULL_HA_GUIDE.md)** - Full HA deployment (Blue-Green + HA Marquez)
- **[ZERO_DOWNTIME_GUIDE.md](ZERO_DOWNTIME_GUIDE.md)** - Zero-downtime switching procedures

### Access and Operations
- **[ACCESSING_MARQUEZ.md](ACCESSING_MARQUEZ.md)** - How to access Marquez UI and API
- **[ALB_ACCESS_GUIDE.md](ALB_ACCESS_GUIDE.md)** - Accessing HA Marquez via ALB

### Optional Enhancements
- **[ECR_SETUP_GUIDE.md](ECR_SETUP_GUIDE.md)** - OPTIONAL: Mirror images to ECR (not required)

### Project Information
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and changes
- **[SECURITY.md](SECURITY.md)** - Security best practices and considerations
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - How to contribute to this project
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** - Community guidelines

## 🎯 Quick Navigation by Use Case

### "I want to deploy for development/testing"
1. Read [README.md](README.md) - Mode 1: Standard Deployment
2. Follow [QUICK_START.md](QUICK_START.md)
3. Access Marquez: [ACCESSING_MARQUEZ.md](ACCESSING_MARQUEZ.md)

### "I need zero-downtime Airflow upgrades"
1. Read [README.md](README.md) - Mode 2: Blue-Green MWAA
2. Follow [BLUE_GREEN_DEPLOYMENT.md](BLUE_GREEN_DEPLOYMENT.md)
3. Learn switching: [ZERO_DOWNTIME_GUIDE.md](ZERO_DOWNTIME_GUIDE.md)

### "I need high availability for lineage tracking"
1. Read [README.md](README.md) - Mode 3: HA Marquez
2. Follow [ALB_ACCESS_GUIDE.md](ALB_ACCESS_GUIDE.md)
3. Understand architecture: [ARCHITECTURE.md](ARCHITECTURE.md)

### "I need production-grade, mission-critical setup"
1. Read [README.md](README.md) - Mode 4: Full HA
2. Follow [FULL_HA_GUIDE.md](FULL_HA_GUIDE.md)
3. Review security: [SECURITY.md](SECURITY.md)

### "I want to compare all deployment options"
1. Read [DEPLOYMENT_MODES.md](DEPLOYMENT_MODES.md)
2. Review cost and features comparison table
3. Choose mode and follow respective guide

## 📋 Deployment Mode Summary

| Mode | Documentation | Cost/Month | Setup Time |
|------|--------------|------------|------------|
| Standard | [README.md](README.md) Mode 1 | ~$350 | 30 min |
| Blue-Green MWAA | [BLUE_GREEN_DEPLOYMENT.md](BLUE_GREEN_DEPLOYMENT.md) | ~$700 | 45 min |
| HA Marquez | [ALB_ACCESS_GUIDE.md](ALB_ACCESS_GUIDE.md) | ~$650 | 35 min |
| Full HA | [FULL_HA_GUIDE.md](FULL_HA_GUIDE.md) | ~$1,000 | 60 min |

## 🔧 Configuration Files

- `cdk.json` - CDK configuration and deployment mode flags
- `requirements.txt` - Python dependencies
- `app.py` - Main CDK application (supports all 4 modes)

## 📁 Code Structure

```
mwaa-openlineage-cdk/
├── app.py                          # Main CDK app (all modes)
├── cdk.json                        # Configuration
├── stacks/                         # CDK stack definitions
│   ├── network_stack.py           # VPC, subnets, security groups
│   ├── marquez_stack.py           # Standard Marquez (EC2)
│   ├── marquez_ha_stack.py        # HA Marquez (ALB+ASG+RDS)
│   ├── mwaa_stack.py              # Standard MWAA
│   └── mwaa_blue_green_stack.py   # Blue-Green MWAA
├── assets/                         # MWAA assets
│   ├── dags/                      # Sample DAGs
│   └── requirements.txt           # Airflow requirements
└── docs/                           # All documentation (this folder)
```

## 🛠️ Scripts

- `switch_zero_downtime.py` - Switch between Blue/Green MWAA environments
- `setup_ecr_marquez.sh` - OPTIONAL: Mirror images to ECR
- `deploy_ha.sh` - Helper script for HA deployment
- `cleanup_all.sh` - Clean up all resources

## ❓ FAQ

**Q: Do I need Docker or ECR setup?**  
A: No. The default deployment uses Docker Hub images and works out of the box. ECR is optional for production optimization.

**Q: Which mode should I choose?**  
A: See [DEPLOYMENT_MODES.md](DEPLOYMENT_MODES.md) for detailed comparison. Quick answer:
- Development/Testing → Standard
- Need Airflow upgrades without downtime → Blue-Green MWAA
- Need lineage HA → HA Marquez
- Production/Mission-critical → Full HA

**Q: Can I switch between modes?**  
A: Yes! See [DEPLOYMENT_MODES.md](DEPLOYMENT_MODES.md) "Switching Between Modes" section.

**Q: How do I access Marquez?**  
A: Depends on deployment:
- Standard/Blue-Green: [ACCESSING_MARQUEZ.md](ACCESSING_MARQUEZ.md)
- HA Marquez/Full HA: [ALB_ACCESS_GUIDE.md](ALB_ACCESS_GUIDE.md)

**Q: What's the difference between Blue-Green and Full HA?**  
A: Blue-Green provides zero-downtime for MWAA only. Full HA adds high availability for Marquez too (ALB+ASG+RDS).

## 📞 Support

- Issues: [GitHub Issues](https://github.com/dgghosalaws/mwaa-openlineage-cdk/issues)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security: [SECURITY.md](SECURITY.md)

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.
