#!/usr/bin/env python3

import os
os.environ['PROJECT_ID'] = 'syntio-ai-ops'

from src.dataplex_components.protected_access import protected_table_access
from google.cloud import bigquery

print('Testing protected table access...')
with protected_table_access(
    bq_table='syntio-ai-ops.chicago_taxi_trips.taxi_trips',
    start_date='2022-09-01',
    end_date='2022-09-01',
    project_id='syntio-ai-ops'
) as view:
    print(f'Created filtered view: {view}')
    client = bigquery.Client()

    # Clean view name for query
    clean_view = view.replace('`', '')
    result = client.query(f'SELECT COUNT(*) as cnt FROM `{clean_view}`').to_dataframe()
    print(f'View has {result.iloc[0].cnt} rows')

    # Test if view metadata is accessible
    table_ref = client.get_table(clean_view)
    print(f'View location: {table_ref.location}')
    print(f'View created: {table_ref.created}')

    print('✅ View creation and access works correctly')