"""
Cost-aware BigQuery client wrapper that estimates and logs costs for all queries.
Requires user approval for expensive queries.
"""
from google.cloud import bigquery
import logging
import os
import sys
from typing import Optional, Union


class CostAwareBigQueryClient:
    """BigQuery client wrapper that estimates costs before running queries"""
    
    def __init__(self, project_id: Optional[str] = None):
        self.client = bigquery.Client(project=project_id)
        self.logger = logging.getLogger(__name__)
        
        # Configuration from environment variables
        self.cost_warning_threshold = float(os.environ.get("BIGQUERY_COST_WARNING_THRESHOLD", "1.0"))
        self.require_approval = os.environ.get("BIGQUERY_REQUIRE_APPROVAL", "true").lower() == "true"
        self.auto_approve_ci = os.environ.get("CI", "false").lower() == "true"  # Skip prompts in CI/CD
        self.max_cost_abort = os.environ.get("BIGQUERY_MAX_COST_ABORT", "false").lower() == "true"  # Hard abort on expensive queries
        self.max_cost_limit = float(os.environ.get("BIGQUERY_MAX_COST_LIMIT", "50.0"))  # Hard limit in production
        
    def estimate_query_cost(self, query: str, job_config: Optional[bigquery.QueryJobConfig] = None) -> tuple[int, float]:
        """Estimate query cost using dry run"""
        if job_config is None:
            job_config = bigquery.QueryJobConfig()
            
        # Create dry run config
        dry_run_config = bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            **{k: v for k, v in job_config._properties.items() if k != 'dryRun'}
        )
        
        try:
            job = self.client.query(query, job_config=dry_run_config)
            bytes_processed = job.total_bytes_processed or 0
            
            # BigQuery pricing: ~$5 per TB (varies by region)
            cost_per_tb = 5.0
            estimated_cost_usd = (bytes_processed / (1024**4)) * cost_per_tb
            estimated_cost_eur = estimated_cost_usd * 0.85  # Rough USD->EUR conversion
            
            return bytes_processed, estimated_cost_eur
            
        except Exception as e:
            self.logger.warning(f"Could not estimate query cost: {e}")
            return 0, 0.0
    
    def _request_user_approval(self, query: str, estimated_cost: float, bytes_processed: int) -> bool:
        """Request user approval for expensive queries"""
        if self.auto_approve_ci:
            self.logger.warning(f"CI environment detected - auto-approving expensive query (€{estimated_cost:.2f})")
            return True
            
        gb_processed = bytes_processed / (1024**3)
        
        print(f"\n⚠️  EXPENSIVE QUERY DETECTED:")
        print(f"💰 Estimated cost: €{estimated_cost:.2f}")
        print(f"📊 Data to process: {gb_processed:.2f} GB")
        print(f"🔍 Query preview: {query[:200]}{'...' if len(query) > 200 else ''}")
        print(f"\n💡 Consider:")
        print(f"   • Adding WHERE clauses with date filtering")  
        print(f"   • Using LIMIT to reduce data processed")
        print(f"   • Breaking query into smaller chunks")
        
        while True:
            try:
                response = input(f"\nProceed with query costing €{estimated_cost:.2f}? [y/N/show]: ").strip().lower()
                
                if response in ['y', 'yes']:
                    print("✅ Query approved by user")
                    return True
                elif response in ['n', 'no', '']:
                    print("❌ Query cancelled by user")
                    return False
                elif response in ['show', 's']:
                    print(f"\n--- FULL QUERY ---")
                    print(query)
                    print("--- END QUERY ---\n")
                    continue
                else:
                    print("Please enter 'y' (yes), 'n' (no), or 'show' to see full query")
                    
            except (EOFError, KeyboardInterrupt):
                print("\n❌ Query cancelled by user (Ctrl+C)")
                return False
    
    def query(self, query: str, job_config: Optional[bigquery.QueryJobConfig] = None, **kwargs):
        """Execute query with cost estimation and logging"""
        
        # Estimate cost first
        bytes_processed, estimated_cost = self.estimate_query_cost(query, job_config)
        
        # Log cost information
        gb_processed = bytes_processed / (1024**3)
        self.logger.info(
            f"💰 Query cost estimate: €{estimated_cost:.4f} "
            f"({gb_processed:.2f} GB processed)"
        )
        
        # Check if approval required for expensive queries
        if estimated_cost > self.cost_warning_threshold and self.require_approval:
            if not self._request_user_approval(query, estimated_cost, bytes_processed):
                raise ValueError(f"Query cancelled by user - estimated cost €{estimated_cost:.2f} exceeds threshold €{self.cost_warning_threshold}")
        elif estimated_cost > self.cost_warning_threshold:
            # Just warn, don't block
            self.logger.warning(
                f"⚠️  EXPENSIVE QUERY: €{estimated_cost:.2f} - "
                f"Consider adding time filtering or LIMIT clauses"
            )
            
        # Execute actual query
        return self.client.query(query, job_config=job_config, **kwargs)
    
    def insert_rows_json(self, *args, **kwargs):
        """Pass through insert operations (no query cost)"""
        return self.client.insert_rows_json(*args, **kwargs)
    
    def get_table(self, *args, **kwargs):
        """Pass through table operations"""
        return self.client.get_table(*args, **kwargs)
        
    def __getattr__(self, name):
        """Pass through all other BigQuery client methods"""
        return getattr(self.client, name)


def get_cost_aware_client(project_id: Optional[str] = None) -> CostAwareBigQueryClient:
    """Factory function to create cost-aware BigQuery client"""
    return CostAwareBigQueryClient(project_id)


# Drop-in replacement for google.cloud.bigquery.Client
class Client(CostAwareBigQueryClient):
    """Drop-in replacement for BigQuery Client with cost awareness"""
    def __init__(self, project=None):
        super().__init__(project_id=project)