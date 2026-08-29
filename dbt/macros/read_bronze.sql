{% macro read_bronze(table_name, ccn_column='facility_id') %}
{#-
    Reads a landed Bronze CSV directly (data/bronze/<table_name>.csv),
    forcing the CCN column to VARCHAR so DuckDB's CSV sniffer never gets a
    chance to infer it as an integer and drop the leading zero — the same
    class of bug fixed in ingest/loader.py, closed again here at the dbt
    read boundary.
-#}
read_csv(
    '{{ var("bronze_dir") }}/{{ table_name }}.csv',
    header = true,
    types = {'{{ ccn_column }}': 'VARCHAR'}
)
{% endmacro %}
