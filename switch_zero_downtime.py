#!/usr/bin/env python3
"""
Zero-Downtime Blue-Green MWAA Switcher

This script provides instant switching between Blue and Green environments
by updating an SSM Parameter Store value. No MWAA downtime required.

Usage:
    python switch_zero_downtime.py --to blue
    python switch_zero_downtime.py --to green
"""

import argparse
import boto3
from botocore.exceptions import ClientError


PARAMETER_NAME = '/mwaa/blue-green/active-environment'


def get_current_active(ssm_client):
    """Get the currently active environment"""
    try:
        response = ssm_client.get_parameter(Name=PARAMETER_NAME)
        return response['Parameter']['Value']
    except ClientError as e:
        if e.response['Error']['Code'] == 'ParameterNotFound':
            print(f"Parameter {PARAMETER_NAME} not found. Creating with default value 'blue'")
            ssm_client.put_parameter(
                Name=PARAMETER_NAME,
                Value='blue',
                Type='String',
                Description='Active MWAA environment for zero-downtime blue-green switching',
                Overwrite=False
            )
            return 'blue'
        raise


def switch_environment(to_env: str, region: str = None):
    """Switch to the specified environment"""
    
    if to_env not in ['blue', 'green']:
        raise ValueError("Environment must be 'blue' or 'green'")
    
    # Initialize AWS client
    session = boto3.Session(region_name=region) if region else boto3.Session()
    ssm = session.client('ssm')
    
    # Get current active environment
    current_active = get_current_active(ssm)
    
    print(f"{'='*60}")
    print(f"Zero-Downtime Blue-Green Switch")
    print(f"{'='*60}")
    print(f"Current Active: {current_active}")
    print(f"Switching To:   {to_env}")
    print(f"{'='*60}")
    
    if current_active == to_env:
        print(f"\n⚠️  {to_env.capitalize()} is already the active environment!")
        print("No action needed.")
        return
    
    # Confirm with user
    response = input(f"\nSwitch from {current_active} to {to_env}? (yes/no): ")
    if response.lower() != 'yes':
        print("Switch cancelled.")
        return
    
    # Update parameter
    print(f"\nUpdating parameter {PARAMETER_NAME}...")
    ssm.put_parameter(
        Name=PARAMETER_NAME,
        Value=to_env,
        Type='String',
        Overwrite=True
    )
    
    print(f"\n{'='*60}")
    print(f"✓ Switch Complete!")
    print(f"{'='*60}")
    print(f"\nActive environment is now: {to_env}")
    print(f"\nWhat happens next:")
    print(f"  1. {to_env.capitalize()} environment DAGs will execute on next scheduled run")
    print(f"  2. {current_active.capitalize()} environment DAGs will skip execution")
    print(f"  3. Running tasks in {current_active} will complete normally")
    print(f"  4. Switch takes effect immediately (no MWAA downtime)")
    print(f"\nTo verify:")
    print(f"  aws ssm get-parameter --name {PARAMETER_NAME} --query 'Parameter.Value' --output text")
    print(f"\nTo switch back:")
    print(f"  python switch_zero_downtime.py --to {current_active}")
    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Zero-downtime switch between Blue and Green MWAA environments',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Switch to Blue environment
  python switch_zero_downtime.py --to blue

  # Switch to Green environment
  python switch_zero_downtime.py --to green --region us-east-1

  # Check current active environment
  aws ssm get-parameter --name /mwaa/blue-green/active-environment --query 'Parameter.Value' --output text
        """
    )
    
    parser.add_argument(
        '--to',
        required=True,
        choices=['blue', 'green'],
        help='Target environment to switch to'
    )
    
    parser.add_argument(
        '--region',
        help='AWS region (default: from AWS CLI config)'
    )
    
    args = parser.parse_args()
    
    try:
        switch_environment(args.to, args.region)
    except Exception as e:
        print(f"\n❌ Error during switch: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
