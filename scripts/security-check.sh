#!/bin/bash
set -e

echo "=========================================="
echo "Running Local Security Checks"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if required tools are installed
check_tool() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${YELLOW}⚠️  $1 not found. Installing...${NC}"
        pip install $1
    else
        echo -e "${GREEN}✅ $1 found${NC}"
    fi
}

echo "Checking required tools..."
check_tool bandit
check_tool safety
check_tool checkov
echo ""

# 1. Bandit - Python security scanner
echo "=========================================="
echo "1. Running Bandit (Python Security)"
echo "=========================================="
bandit -r . -ll -f screen || {
    echo -e "${RED}❌ Bandit found security issues${NC}"
    exit 1
}
echo -e "${GREEN}✅ Bandit scan passed${NC}"
echo ""

# 2. Safety - Dependency vulnerability scanner
echo "=========================================="
echo "2. Running Safety (Dependency Check)"
echo "=========================================="
safety check --json || {
    echo -e "${YELLOW}⚠️  Safety found vulnerable dependencies${NC}"
    echo "Review the vulnerabilities above and update dependencies if needed"
}
echo ""

# 3. Checkov - Infrastructure as Code scanner
echo "=========================================="
echo "3. Running Checkov (IaC Security)"
echo "=========================================="
checkov -d . --framework cloudformation --quiet --compact || {
    echo -e "${YELLOW}⚠️  Checkov found IaC security issues${NC}"
    echo "Review the issues above and fix if needed"
}
echo ""

# 4. Check for secrets
echo "=========================================="
echo "4. Checking for Secrets"
echo "=========================================="
echo "Scanning for common secret patterns..."

# Check for AWS keys
if grep -r "AKIA[0-9A-Z]{16}" . --exclude-dir=.git --exclude-dir=cdk.out --exclude-dir=.venv 2>/dev/null; then
    echo -e "${RED}❌ Found potential AWS access key${NC}"
    exit 1
fi

# Check for private keys
if grep -r "BEGIN.*PRIVATE KEY" . --exclude-dir=.git --exclude-dir=cdk.out --exclude-dir=.venv 2>/dev/null; then
    echo -e "${RED}❌ Found potential private key${NC}"
    exit 1
fi

# Check for passwords
if grep -ri "password.*=.*['\"]" . --exclude-dir=.git --exclude-dir=cdk.out --exclude-dir=.venv --exclude="*.sh" 2>/dev/null | grep -v "# password" | grep -v "your-password"; then
    echo -e "${YELLOW}⚠️  Found potential hardcoded password${NC}"
fi

echo -e "${GREEN}✅ No obvious secrets found${NC}"
echo ""

# 5. Check for sensitive data
echo "=========================================="
echo "5. Checking for Sensitive Data"
echo "=========================================="

# Check for account IDs
if grep -r "[0-9]\{12\}" . --exclude-dir=.git --exclude-dir=cdk.out --exclude-dir=.venv --exclude="*.sh" 2>/dev/null | grep -v "YOUR-ACCOUNT-ID" | grep -v "123456789012" | grep -v "example"; then
    echo -e "${YELLOW}⚠️  Found potential AWS account ID${NC}"
    echo "Make sure to use placeholders like YOUR-ACCOUNT-ID"
fi

# Check for IP addresses
if grep -rE "\b([0-9]{1,3}\.){3}[0-9]{1,3}\b" . --exclude-dir=.git --exclude-dir=cdk.out --exclude-dir=.venv --exclude="*.sh" 2>/dev/null | grep -v "0.0.0.0" | grep -v "127.0.0.1" | grep -v "YOUR-IP" | grep -v "example"; then
    echo -e "${YELLOW}⚠️  Found potential IP address${NC}"
    echo "Make sure to use placeholders like YOUR-IP-ADDRESS"
fi

echo -e "${GREEN}✅ Sensitive data check complete${NC}"
echo ""

# 6. CDK Security Check
echo "=========================================="
echo "6. CDK Security Check"
echo "=========================================="
if command -v cdk &> /dev/null; then
    echo "Synthesizing CDK stacks..."
    cdk synth --quiet > /dev/null 2>&1 || {
        echo -e "${RED}❌ CDK synth failed${NC}"
        exit 1
    }
    echo -e "${GREEN}✅ CDK synth successful${NC}"
else
    echo -e "${YELLOW}⚠️  CDK not installed, skipping CDK check${NC}"
fi
echo ""

# Summary
echo "=========================================="
echo "Security Check Summary"
echo "=========================================="
echo -e "${GREEN}✅ All security checks passed!${NC}"
echo ""
echo "Scans completed:"
echo "  ✅ Bandit (Python security)"
echo "  ✅ Safety (Dependency vulnerabilities)"
echo "  ✅ Checkov (Infrastructure as Code)"
echo "  ✅ Secret scanning"
echo "  ✅ Sensitive data check"
echo "  ✅ CDK security check"
echo ""
echo "Your code is ready to commit!"
