{% macro generate_schema_name(custom_schema_name, node) -%}
    {#-
        dbt's default behavior prefixes a custom schema with the target
        schema (e.g. "main_marts"). We want clean, predictable schema names
        ("staging", "marts") since the Streamlit app's AI layer queries them
        by exact name.
    -#}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
