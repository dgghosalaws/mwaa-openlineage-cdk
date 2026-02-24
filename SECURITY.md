# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly:

1. **DO NOT** create a public GitHub issue
2. Email: Create an issue with label `security` and mark it as private
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within 48 hours and work with you to address the issue.

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Security Best Practices

### For Deployment

1. **Never commit credentials or secrets**
   - No AWS access keys
   - No passwords
   - No API tokens
   - Use AWS Secrets Manager or Parameter Store

2. **Use IAM roles, not access keys**
   - Assign roles to EC2 instances
   - Use IAM roles for MWAA
   - Enable MFA for AWS accounts

3. **Network Security**
   - Use private subnets for production
   - Implement VPN or AWS Client VPN for access
   - Use security groups with least privilege
   - Enable VPC Flow Logs

4. **Encryption**
   - Use KMS customer-managed keys
   - Enable encryption at rest for S3
   - Enable encryption for MWAA
   - Enable key rotation

5. **Monitoring and Logging**
   - Enable CloudTrail for API logging
   - Enable VPC Flow Logs
   - Monitor CloudWatch logs
   - Set up CloudWatch alarms

6. **Access Control**
   - Implement least privilege IAM policies
   - Use MWAA private webserver access
   - Restrict security group rules
   - Use IP allowlisting where appropriate

7. **Compliance**
   - Follow AWS Well-Architected Framework
   - Implement CIS AWS Foundations Benchmark
   - Regular security audits
   - Document compliance requirements

### For Development

1. **Code Security**
   - Run security scanners (Bandit, Safety)
   - Keep dependencies updated
   - Review CDK synthesized templates
   - Use CDK security best practices

2. **Git Security**
   - Never commit sensitive data
   - Use .gitignore properly
   - Review commits before pushing
   - Use signed commits

3. **Testing**
   - Write security tests
   - Test IAM policies
   - Test network isolation
   - Test encryption

## Known Security Considerations

### Current Configuration

This project is configured for **development/demo** purposes with:

- ✅ S3 managed encryption (consider KMS for production)
- ✅ Security groups with specific rules
- ✅ IAM roles with least privilege
- ⚠️ Public subnet for Marquez (move to private for production)
- ⚠️ Public webserver access for MWAA (use private for production)

### Production Hardening Required

Before using in production:

1. **Move to Private Subnets**
   ```python
   # In marquez_stack.py
   vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE)
   
   # In mwaa_stack.py
   webserver_access_mode="PRIVATE_ONLY"
   ```

2. **Enable KMS Encryption**
   ```python
   # Create KMS key
   kms_key = kms.Key(
       self, "MwaaKmsKey",
       enable_key_rotation=True,
       description="KMS key for MWAA encryption"
   )
   
   # Use in S3 and MWAA
   encryption=s3.BucketEncryption.KMS,
   encryption_key=kms_key
   ```

3. **Enable Audit Logging**
   - CloudTrail for API calls
   - VPC Flow Logs for network traffic
   - AWS Config for compliance

4. **Implement Backup Strategy**
   - Enable AWS Backup for EC2
   - S3 versioning (already enabled)
   - Document restore procedures

## Security Checklist

### Before Deployment

- [ ] Review all IAM policies
- [ ] Check security group rules
- [ ] Verify encryption settings
- [ ] Review network configuration
- [ ] Check for hardcoded credentials
- [ ] Review CloudFormation templates
- [ ] Test in non-production first

### After Deployment

- [ ] Enable CloudTrail
- [ ] Enable VPC Flow Logs
- [ ] Set up CloudWatch alarms
- [ ] Configure AWS Config rules
- [ ] Test security controls
- [ ] Document access procedures
- [ ] Schedule security reviews

### Regular Maintenance

- [ ] Update dependencies monthly
- [ ] Review IAM policies quarterly
- [ ] Audit access logs monthly
- [ ] Test disaster recovery quarterly
- [ ] Review security groups monthly
- [ ] Update documentation as needed

## Compliance

This project is designed to support:

- **AWS Well-Architected Framework**
  - Security Pillar
  - Reliability Pillar
  - Operational Excellence Pillar

- **CIS AWS Foundations Benchmark**
  - IAM best practices
  - Logging and monitoring
  - Networking security

- **NIST Cybersecurity Framework**
  - Identify
  - Protect
  - Detect
  - Respond
  - Recover

## Security Resources

### AWS Security

- [AWS Security Best Practices](https://aws.amazon.com/security/best-practices/)
- [AWS Well-Architected Security Pillar](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html)
- [MWAA Security](https://docs.aws.amazon.com/mwaa/latest/userguide/security.html)
- [CDK Security Best Practices](https://docs.aws.amazon.com/cdk/latest/guide/best-practices.html#best-practices-security)

### Tools

- [AWS Security Hub](https://aws.amazon.com/security-hub/)
- [AWS GuardDuty](https://aws.amazon.com/guardduty/)
- [AWS Inspector](https://aws.amazon.com/inspector/)
- [AWS Config](https://aws.amazon.com/config/)

### Scanning Tools

- [Bandit](https://github.com/PyCQA/bandit) - Python security scanner
- [Safety](https://github.com/pyupio/safety) - Dependency vulnerability scanner
- [Checkov](https://www.checkov.io/) - Infrastructure as code scanner
- [TruffleHog](https://github.com/trufflesecurity/trufflehog) - Secret scanner

## Contact

For security concerns or questions:
- Create a private security issue on GitHub
- Tag with `security` label
- We will respond within 48 hours

## Acknowledgments

We appreciate responsible disclosure of security vulnerabilities. Contributors who report valid security issues will be acknowledged (with permission) in our security advisories.

---

**Last Updated:** February 9, 2026  
**Version:** 1.0.0
