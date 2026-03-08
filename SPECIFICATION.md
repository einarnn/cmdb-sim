# SPECIFICATION OF CMDB SIMULATOR

## Introduction

This project is targeting providing a simple http(s) server that can serve initially randomly generated data that looks like it came from a ServeiceNow database. The section "Sample Data" shows the data.

## Baseline Instructions

* Python with `asyncio` and `aiohttp` for http(s)
* Postgres if a database is required
* All apps and tools must be containerized
* Comprehensive Docker Compose file MUST be provided
* Use slim base image for application
* Use Alpine-based image for Postgres
* No performance/SLO expectations
* Log all operations to console
* Automatically limit container logs to 3 files rotating, each file max 50MB
  * log format should be plain text with microsecond timestamp

## Requirements

* Provide a script to generate self-signed PEM-encoded CA cert and key and a server cert and key, placing the script in a subdirectory `certs`
  * Provide an option to incrementally regenerate the server cert and add an option to provide an IP address to set as an IP SAN
* Simple http server
  * Support http operations on port 80 always
  * Support https operations on port 443 when TLS certs configured
  * Optional auto-generated certs or provided certs to enable TLS support. Control via environment variables identifying container local paths to PEM-encoded files:
    * CA_CERT
    * SERVER_CERT
    * SERVER_KEY
  * Ensure compose file has sample cert bind mapping at **file** level
  * Support `/healthz` & `/readyz` endpoints for Docker and specify them in compose file
* Base API endpoint `/api/v1/cmdb`
* Take environment variable parameter detailing how many records MUST be supported at initialization:
  * Environment variable CMDB_RECORD_COUNT
  * Minimum: 1
  * Default: 10000
  * Maximum: 10000000
* Optional persistence controlled by environment variable at `docker compose up` time:
  * If environment variable CMDB_PERSIST is set to `1` or `true`, persist data in Postgres. Otherwise, data is transient.
* Auto-generation of sample data that is maintained for run of tool
  * Support for random incremental changes to data:
    * Update `sys_updated_on` to current time
      * Format of `sys_updated_on` MUST be `YYYY-MM-DD HH:MM:SS`
    * Modify `u_segmentation_group_tag`
    * Toggle `u_sync` randomly between true and false
    * Randomly monotonically increment `sys_mod_count`
  * Mutate records at a maximum rate of 1000 per hour
  * Mutation should be random across time
* Support API that allows the entire set of records to be returned. This API MUST have the following characteristics:
  * GET only
  * `/api/v1/cmdb` plus query parameter(s)
  * Sort order MUST be by `sys_updated_on` ascending
  * Query parameter supporting filtering by relational operfators on `sys_updated_on`
    * Support gt/gte/lt/lte/eq
    * Relational operator appears **between** LHS and RHS in query string as one of:
      * `.gt.`
      * `.gte.`
      * `.lt.`
      * `.lte.`
      * `.eq.`
    * Query format MUST be `...?sys_updated_on.gte.YYYY-MM-DD HH:MM:SS` (appropriately URL query encoded)
* Query APIs always return full set of records
  * Optimize implementationm to stream data where appropriate
* Keep sample data's typing, i.e. mostly strings and a single int

## Sample Data

The sample CMDB data in Python format is:

```python
CMDB = '''{
  "result": [
    {
      "u_account_name": "W22067",
      "u_macaddress": "00:00:00:00:56:33",
      "u_processed": "2021-08-09 16:48:42",
      "u_segmentation_group_tag": "cts:security-group-tag=2774-000",
      "sys_mod_count": 0,
      "u_hostname": "Test_22067",
      "sys_updated_on": "2021-08-09 16:48:42",
      "sys_tags": "",
      "u_community_group": "Administration",
      "sys_id": "8801067edbf974147a136ac2ca96192f",
      "u_config_item": "SNtoDataMart22067",
      "u_sync": "false",
      "sys_updated_by": "DGS06_admin",
      "u_id": "",
      "sys_created_on": "2021-08-09 16:48:42",
      "u_ci_status": "Operational",
      "u_host_name": "Test_22067",
      "sys_created_by": "DGS06_admin"
    },
    {
      "u_account_name": "W4679",
      "u_macaddress": "00:00:00:00:12:47",
      "u_processed": "2021-08-03 16:20:28",
      "u_segmentation_group_tag": "cts:security-group-tag=2774-000",
      "sys_mod_count": 0,
      "u_hostname": "Test_4679",
      "sys_updated_on": "2021-08-03 16:20:28",
      "sys_tags": "",
      "u_community_group": "Administration",
      "sys_id": "08018b741b3db0908883ea02b24bcb16",
      "u_config_item": "SNtoDataMart4679",
      "u_sync": "false",
      "sys_updated_by": "DGS06_admin",
      "u_id": "",
      "sys_created_on": "2021-08-03 16:20:28",
      "u_ci_status": "Operational",
      "u_host_name": "Test_4679",
      "sys_created_by": "DGS06_admin"
    },
    {
      "u_account_name": "W1977",
      "u_macaddress": "00:00:00:00:07:b9",
      "u_processed": "2021-08-03 14:09:24",
      "u_segmentation_group_tag": "cts:security-group-tag=2774-000",
      "sys_mod_count": 0,
      "u_hostname": "Test_1977",
      "sys_updated_on": "2021-08-03 14:09:24",
      "sys_tags": "",
      "u_community_group": "Administration",
      "sys_id": "88036af41b3970908883ea02b24bcb5c",
      "u_config_item": "SNtoDataMart1977",
      "u_sync": "false",
      "sys_updated_by": "DGS06_admin",
      "u_id": "",
      "sys_created_on": "2021-08-03 14:09:24",
      "u_ci_status": "Operational",
      "u_host_name": "Test_1977",
      "sys_created_by": "DGS06_admin"
    }
}
```
