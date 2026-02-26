"""
DR State Management Plugin for MWAA

This plugin automatically checks the DR state before DAG runs.
If the current region is not active, DAG runs are skipped.

IMPORTANT: Failover is INSTANT - no MWAA environment update needed!
- DR_ENABLED is set ONCE during deployment
- Plugin reads DynamoDB dynamically at runtime
- Failover = update DynamoDB (takes seconds, not 20-30 minutes)

Environment Variables (set once during deployment):
- DR_ENABLED: Set to 'true' to enable DR checks (default: false)
- DR_STATE_TABLE: DynamoDB table name (default: mwaa-openlineage-dr-state-dev)
- DR_STATE_SOURCE: 'dynamodb' or 'parameter_store' (default: dynamodb)
- DR_PARAMETER_NAME: Parameter Store path (default: /mwaa/dr/active-region)
- AWS_REGION: Current AWS region (auto-set by MWAA)

Usage:
1. Add this file to your MWAA plugins.zip
2. Set DR_ENABLED=true in MWAA environment variables (ONE TIME)
3. All DAG runs will automatically check DR state from DynamoDB

Failover Process (INSTANT):
1. Update DynamoDB: active_region = 'us-east-1' (1 second)
2. Plugin reads new value on next DAG run (instant)
3. No MWAA environment update needed!

Behavior:
- If region is active: DAGs run normally
- If region is inactive: DAG runs are marked as SKIPPED
- On error: Fails open (allows execution) to prevent outages
"""

from airflow.listeners import hookimpl
from airflow.utils.state import DagRunState
from airflow.configuration import conf
import boto3
import os
import logging

logger = logging.getLogger(__name__)


class DRStateListener:
    """
    Airflow listener that enforces DR state before DAG execution.
    
    This listener intercepts all DAG runs and checks if the current
    region is the active region. If not, the DAG run is skipped.
    
    Supports two state sources:
    1. DynamoDB Global Table (default, recommended)
    2. Parameter Store (alternative, requires cross-region reads)
    """
    
    def __init__(self):
        # Try both methods: Airflow config API and environment variables
        # MWAA stores airflow-configuration-options as environment variables
        # Pattern: AIRFLOW__SECTION__KEY
        
        # Method 1: Use Airflow's configuration API (recommended)
        try:
            dr_enabled_str = conf.get('dr', 'enabled', fallback='false')
            logger.info(f"DR config from Airflow API: dr.enabled = '{dr_enabled_str}'")
        except Exception as e:
            logger.info(f"Could not read from Airflow config API: {e}")
            # Method 2: Fall back to environment variable
            dr_enabled_str = os.environ.get('AIRFLOW__DR__ENABLED', 'false')
            logger.info(f"DR config from env var: AIRFLOW__DR__ENABLED = '{dr_enabled_str}'")
        
        self.dr_enabled = dr_enabled_str.lower() == 'true'
        
        if not self.dr_enabled:
            logger.info("DR state checking is DISABLED (set dr.enabled=true to enable)")
            return
        
        # Configuration
        try:
            self.state_source = conf.get('dr', 'state_source', fallback='dynamodb').lower()
        except:
            self.state_source = os.environ.get('AIRFLOW__DR__STATE_SOURCE', 'dynamodb').lower()
        
        self.current_region = os.environ.get('AWS_REGION')
        
        # Exclude DR management DAGs from state checking
        self.excluded_dags = [
            'dr_backup_metadata',
            'dr_restore_metadata',
            'dr_health_check',
        ]
        
        # Initialize state source
        if self.state_source == 'dynamodb':
            self._init_dynamodb()
        elif self.state_source == 'parameter_store':
            self._init_parameter_store()
        else:
            logger.error(f"Invalid DR_STATE_SOURCE: {self.state_source}")
            self.dr_enabled = False
    
    def _init_dynamodb(self):
        """Initialize DynamoDB state source"""
        try:
            self.table_name = conf.get('dr', 'state_table', fallback='mwaa-openlineage-dr-state-dev')
        except:
            self.table_name = os.environ.get('AIRFLOW__DR__STATE_TABLE', 'mwaa-openlineage-dr-state-dev')
        
        try:
            self.dynamodb = boto3.resource('dynamodb')
            self.table = self.dynamodb.Table(self.table_name)
            logger.info(
                f"DR state checking ENABLED (DynamoDB) - "
                f"table: {self.table_name}, "
                f"region: {self.current_region}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize DynamoDB: {e}")
            self.dr_enabled = False
    
    def _init_parameter_store(self):
        """Initialize Parameter Store state source"""
        self.parameter_name = os.environ.get('AIRFLOW__DR__PARAMETER_NAME', '/mwaa/dr/active-region')
        
        try:
            self.ssm = boto3.client('ssm')
            logger.info(
                f"DR state checking ENABLED (Parameter Store) - "
                f"parameter: {self.parameter_name}, "
                f"region: {self.current_region}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Parameter Store: {e}")
            self.dr_enabled = False
    
    def is_active_region(self):
        """
        Check if current region is the active region.
        
        Returns:
            bool: True if active, False if not active
            
        Fail-safe: Returns True on any error (fail open)
        """
        if not self.dr_enabled:
            return True
        
        if self.state_source == 'dynamodb':
            return self._check_dynamodb_state()
        elif self.state_source == 'parameter_store':
            return self._check_parameter_store_state()
        else:
            return True
    
    def _check_dynamodb_state(self):
        """Check state from DynamoDB Global Table"""
        try:
            response = self.table.get_item(Key={'state_id': 'ACTIVE_REGION'})
            
            if 'Item' not in response:
                logger.warning(
                    "DR state not found in DynamoDB - "
                    "allowing execution (fail open)"
                )
                return True
            
            active_region = response['Item'].get('active_region')
            is_active = active_region == self.current_region
            
            if not is_active:
                logger.info(
                    f"Region check (DynamoDB): active={active_region}, "
                    f"current={self.current_region} - "
                    f"DAG execution will be SKIPPED"
                )
            
            return is_active
            
        except Exception as e:
            logger.error(
                f"Error checking DynamoDB state: {e} - "
                f"allowing execution (fail open)"
            )
            return True
    
    def _check_parameter_store_state(self):
        """Check state from Parameter Store"""
        try:
            response = self.ssm.get_parameter(Name=self.parameter_name)
            active_region = response['Parameter']['Value']
            is_active = active_region == self.current_region
            
            if not is_active:
                logger.info(
                    f"Region check (Parameter Store): active={active_region}, "
                    f"current={self.current_region} - "
                    f"DAG execution will be SKIPPED"
                )
            
            return is_active
            
        except Exception as e:
            logger.error(
                f"Error checking Parameter Store state: {e} - "
                f"allowing execution (fail open)"
            )
            return True
    
    @hookimpl
    def on_dag_run_running(self, dag_run, msg):
        """
        Called when a DAG run transitions to RUNNING state.
        
        If this region is not active, marks the DAG run as SKIPPED.
        
        Args:
            dag_run: The DAG run object
            msg: Optional message
        """
        if not self.dr_enabled:
            return
        
        # Don't check state for DR management DAGs
        if dag_run.dag_id in self.excluded_dags:
            logger.debug(f"Skipping DR check for excluded DAG: {dag_run.dag_id}")
            return
        
        if not self.is_active_region():
            logger.info(
                f"Skipping DAG run {dag_run.dag_id} "
                f"(run_id: {dag_run.run_id}) - not active region"
            )
            
            # Mark DAG run as skipped
            dag_run.set_state(DagRunState.SKIPPED)
            
            # Add note to DAG run log
            try:
                dag_run.log.info(
                    f"DAG run skipped by DR state plugin - "
                    f"active region is not {self.current_region}"
                )
            except:
                pass  # Log might not be available


# Register the listener
listener = DRStateListener()
