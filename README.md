# ENV3 – TIBCO Case Resubmit

A Flask web application for searching and resubmitting failed TIBCO iProcess cases.

## Features
- Secure login page (configurable credentials)
- Search by **Case Number** and/or **GUID**
- Results page titled **"ENV3-Case Resubmit Process"**
- Reads from Platform Support DB and TIBCO Case Data table
- Displays: iProcess Procedure, MessageIdentifier, AdviserIdentifier, ClientIdentifier, MessageType/Queue, Status, CreateDateTime, CompleteDateTime
- **View Message Body** popup
- **Resubmit** flow with confirmation and mandatory reason capture
- Matches AJ Bell styling of TIBCO Audit Viewer

## Quick Start

```bash
cd c:\case_resubmit
install_packages.bat    # first time only
run_app.bat
```

Open http://localhost:5000 — log in with **admin / admin123**.

## Configuration

Copy `.env.example` to `.env` (already done) and fill in real DB credentials:

| Variable | Description |
|---|---|
| `APP_USERNAME` | Login username |
| `APP_PASSWORD` | Login password |
| `PLATFORM_DB_SERVER` | Platform Support SQL Server hostname |
| `PLATFORM_DB_NAME` | Platform Support database name |
| `TIBCO_DB_SERVER` | TIBCO Case Data SQL Server hostname |
| `TIBCO_DB_NAME` | TIBCO database name |

When no database connection is available the application runs in **demo mode**
and displays sample records so the UI can be verified.

## Database Tables Used

| Database | Table / Object | Purpose |
|---|---|---|
| PlatformSupportDB | `dbo.PlatformSupportMessages` | Message queue records |
| PlatformSupportDB | `dbo.ResubmitAuditLog` | Logs every resubmit action |
| PlatformSupportDB | `dbo.usp_ResubmitCase` | Stored proc triggered on resubmit |
| tibcodomain | `swpro.case_data` | Case field/value pairs |
