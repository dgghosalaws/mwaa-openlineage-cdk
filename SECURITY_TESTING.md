# Security Testing Guide

This document describes the security testing setup and how to use it.

## Overview

This project uses multiple layers of security testing:

1. **Automated GitHub Actions** - Runs on every push/PR
2. **Pre-commit Hooks** - Runs before each commit
3. **Local Security Scripts** - Run manually anytime
4. **Dependabot** - Automated dependency updates

## Automated Security Scans

### GitHub Actions Workflows

#### 1. Security Scan (`.github/workflows/security.yml`)

Runs on:
- Every push to `main` or `develop`
- Every pull request
- Weekly on Monday at 9am UTC

**Scans performed:**
- **Bandit**: Scans Python code for security vulnerabilities
- **Safety**: Checks dependencies for known vulnerabilities
- **Checkov**: Scans CDK/CloudFormation for security issues
- **TruffleHog**: Detects secrets in code and git history
- **CodeQL**: Advanced semantic code analysis

**View results:**
- Go to GitHub Actions tab
- Click on latest workflow run
- Download security reports from artifacts

#### 2. Code Quality (`.github/workflows/code-quality.yml`)

Runs on:
- Every push to `main` or `develop`
- Every pull request

**Checks performed:**
- Black (code formatting)
- isort (import sorting)
- Flake8 (linting)
- Pylint (code analysis)
- MyPy (type checking)
- CDK synth validation

#### 3. Dependency Review

Runs on:
- Every pull request

**Checks:**
- Reviews dependency changes
- Fails on moderate+ severity vulnerabilities
- Provides detailed vulnerability information

### Dependabot

Automatically creates PRs for:
- Python dependency updates (weekly)
- GitHub Actions updates (weekly)

**Configuration:** `.github/dependabot.yml`

## Local Security Testing

### Quick Security Check

Run all security checks locally:

```bash
./scripts/security-check.sh
```

This script:
1. Installs required tools (bandit, safety, checkov)
2. Runs Python security scan
3. Checks for vulnerable dependencies
4. Scans infrastructure code
5. Searches for secrets
6. Checks for sensitive data
7. Validates CDK synthesis

**Exit codes:**
- `0`: All checks passed
- `1`: Security issues found

### Individual Tool Usage

#### Bandit (Python Security)

```bash
# Scan all Python files
bandit -r . -ll

# Scan with detailed output
bandit -r . -f json -o bandit-report.json

# Scan specific severity
bandit -r . -ll  # Low and above
bandit -r . -lll # Medium and above
```

**Common issues detected:**
- Hardcoded passwords
- SQL injection vulnerabilities
- Use of insecure functions
- Weak cryptography

#### Safety (Dependency Vulnerabilities)

```bash
# Check all dependencies
safety check

# Check with JSON output
safety check --json

# Check specific file
safety check -r requirements.txt
```

**What it checks:**
- Known CVEs in dependencies
- Severity levels
- Affected versions
- Remediation advice

#### Checkov (IaC Security)

```bash
# Scan all infrastructure code
checkov -d .

# Scan CloudFormation only
checkov -d . --framework cloudformation

# Scan with specific checks
checkov -d . --check CKV_AWS_18  # S3 bucket logging

# Skip specific checks
checkov -d . --skip-check CKV_AWS_18
```

**Common issues detected:**
- Unencrypted resources
- Public access enabled
- Missing logging
- Weak security groups
- Missing backup policies

#### Secret Detection

```bash
# Check for AWS keys
grep -r "AKIA[0-9A-Z]{16}" . --exclude-dir=.git

# Check for private keys
grep -r "BEGIN.*PRIVATE KEY" . --exclude-dir=.git

# Check for passwords
grep -ri "password.*=" . --exclude-dir=.git
```

## Pre-commit Hooks

### Setup

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
cd mwaa-openlineage-cdk
pre-commit install
```

### Usage

Hooks run automatically on `git commit`. To run manually:

```bash
# Run on all files
pre-commit run --all-files

# Run specific hook
pre-commit run bandit --all-files
pre-commit run detect-secrets --all-files

# Skip hooks (not recommended)
git commit --no-verify
```

### Configured Hooks

1. **bandit**: Python security scanner
2. **detect-secrets**: Secret detection
3. **black**: Code formatting
4. **isort**: Import sorting
5. **flake8**: Linting
6. **check-yaml**: YAML validation
7. **check-json**: JSON validation
8. **detect-private-key**: Private key detection
9. **checkov**: IaC security

## Security Testing Best Practices

### Before Committing

1. **Run local security check**:
   ```bash
   ./scripts/security-check.sh
   ```

2. **Fix any issues found**:
   - High severity: Must fix before commit
   - Medium severity: Should fix before commit
   - Low severity: Can fix later

3. **Verify no secrets**:
   - No AWS keys
   - No passwords
   - No API tokens

### Before Creating PR

1. **Run all checks**:
   ```bash
   pre-commit run --all-files
   ./scripts/security-check.sh
   cdk synth
   ```

2. **Review changes**:
   - No sensitive data added
   - No security regressions
   - Dependencies are up to date

3. **Check GitHub Actions**:
   - All workflows pass
   - No security warnings

### Reviewing PRs

1. **Check automated scans**:
   - Security workflow passed
   - Code quality workflow passed
   - Dependency review passed

2. **Review security reports**:
   - Download artifacts
   - Review any warnings
   - Verify fixes for issues

3. **Manual review**:
   - Check for hardcoded values
   - Verify IAM permissions
   - Review security group rules

## Common Security Issues

### 1. Hardcoded Credentials

**Bad:**
```python
aws_access_key = "AKIAIOSFODNN7EXAMPLE"
password = "mypassword123"
```

**Good:**
```python
# Use AWS IAM roles
# Use Secrets Manager
secret = secretsmanager.Secret(self, "Secret")
```

### 2. Hardcoded Account IDs

**Bad:**
```python
account_id = "123456789012"
```

**Good:**
```python
account_id = cdk.Aws.ACCOUNT_ID  # Use CDK context
# Or in docs: YOUR-ACCOUNT-ID
```

### 3. Public Access

**Bad:**
```python
webserver_access_mode="PUBLIC_ONLY"
```

**Good (for production):**
```python
webserver_access_mode="PRIVATE_ONLY"
```

### 4. Unencrypted Resources

**Bad:**
```python
bucket = s3.Bucket(self, "Bucket")
```

**Good:**
```python
bucket = s3.Bucket(
    self, "Bucket",
    encryption=s3.BucketEncryption.KMS,
    encryption_key=kms_key
)
```

### 5. Overly Permissive Security Groups

**Bad:**
```python
security_group.add_ingress_rule(
    ec2.Peer.any_ipv4(),
    ec2.Port.tcp(22)
)
```

**Good:**
```python
security_group.add_ingress_rule(
    ec2.Peer.ipv4("10.0.0.0/8"),  # Specific CIDR
    ec2.Port.tcp(22)
)
```

## Fixing Security Issues

### High Severity

**Must fix immediately:**
1. Hardcoded credentials
2. SQL injection vulnerabilities
3. Remote code execution risks
4. Exposed secrets

**Actions:**
- Remove from code
- Rotate compromised credentials
- Update dependencies
- Add security controls

### Medium Severity

**Should fix before merge:**
1. Weak encryption
2. Missing authentication
3. Insecure configurations
4. Vulnerable dependencies

**Actions:**
- Update configurations
- Add security controls
- Update dependencies
- Document exceptions

### Low Severity

**Can fix later:**
1. Code quality issues
2. Minor configuration issues
3. Documentation gaps

**Actions:**
- Create issue to track
- Fix in next sprint
- Document workarounds

## Security Exceptions

If you need to suppress a security warning:

### Bandit

```python
# nosec B101
password = get_password()  # nosec
```

### Checkov

```python
# checkov:skip=CKV_AWS_18:Reason for skip
```

**Important:** Always document why the exception is needed!

## Continuous Monitoring

### Weekly Tasks

1. **Review Dependabot PRs**:
   - Check for security updates
   - Test and merge promptly

2. **Review security scan results**:
   - Check GitHub Actions
   - Review any new warnings

3. **Update dependencies**:
   ```bash
   pip list --outdated
   pip install --upgrade package-name
   ```

### Monthly Tasks

1. **Security audit**:
   - Run full security scan
   - Review all findings
   - Update security documentation

2. **Dependency review**:
   - Check for EOL packages
   - Plan major version updates

3. **Access review**:
   - Review IAM policies
   - Review security groups
   - Remove unused resources

## Resources

### Tools Documentation

- **Bandit**: https://bandit.readthedocs.io/
- **Safety**: https://pyup.io/safety/
- **Checkov**: https://www.checkov.io/
- **TruffleHog**: https://github.com/trufflesecurity/trufflehog
- **CodeQL**: https://codeql.github.com/
- **Pre-commit**: https://pre-commit.com/

### Security Best Practices

- **AWS Security**: https://aws.amazon.com/security/
- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **CIS Benchmarks**: https://www.cisecurity.org/cis-benchmarks/
- **NIST Cybersecurity**: https://www.nist.gov/cyberframework

### Getting Help

1. **Security issues**: Create private security advisory on GitHub
2. **Questions**: Open GitHub issue with `security` label
3. **Urgent issues**: Contact maintainers directly

## Summary

Security testing is integrated at every level:
- ✅ Automated scans on every push
- ✅ Pre-commit hooks prevent issues
- ✅ Local scripts for quick checks
- ✅ Dependabot keeps dependencies updated
- ✅ Comprehensive documentation

**Remember:** Security is everyone's responsibility!
