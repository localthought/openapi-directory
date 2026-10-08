# Airtable read-only subset provenance

This OpenAPI document covers the read operations used for Airtable base
discovery, base schema discovery, and record synchronization. It was checked
against Airtable's official Web API reference on 2026-10-08.

- [List bases](https://airtable.com/developers/web/api/list-bases)
- [Get base schema](https://airtable.com/developers/web/api/get-base-schema)
- [List records](https://airtable.com/developers/web/api/list-records)
- [OAuth reference](https://airtable.com/developers/web/api/oauth-reference)
- [Authentication reference](https://airtable.com/developers/web/api/authentication)
- [Scopes reference](https://airtable.com/developers/web/api/scopes)
- [Pagination and record limits](https://support.airtable.com/articles/6292134965-getting-started-with-airtable-s-web-api)

OAuth uses Airtable's authorization-code flow with PKCE. Each operation
declares only the scope it needs: `schema.bases:read` for base and table
metadata, or `data.records:read` for table records. Record field names and
value shapes are user-defined, so the OpenAPI schema preserves arbitrary JSON
values under `fields`. The `offset` pagination token is opaque and must be
passed through unchanged.
