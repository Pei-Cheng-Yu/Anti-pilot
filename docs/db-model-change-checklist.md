# DB Model Change Checklist

When changing a DB model, do not stop at `backend/app/db/model.py`. Most product and agent flows return Pydantic schemas through services and MCP tools, so a DB-only change can break runtime behavior even if the database migration succeeds.

## Why This Matters

The common backend path is:

```text
DB model row
-> service mapper
-> Pydantic schema/entity
-> MCP/API response
-> agent or frontend consumes structured data
```

If these layers drift, agents can fail because they do not receive the field they need, or Pydantic validation can fail when a DB value does not match the schema.

## Change Checklist

When adding, removing, renaming, or changing a DB model field:

1. Update the DB model.

   Check:

   ```text
   backend/app/db/model.py
   ```

2. Add or update the Alembic migration.

   Include a safe migration path:

   - For new required fields, add a DB default or backfill existing rows before enforcing non-null.
   - For renamed fields, migrate existing data.
   - For enum-like strings, consider a DB check constraint if the values must be strict.

3. Update Pydantic schemas/entities.

   Check:

   ```text
   backend/app/schema/entities.py
   backend/app/validators/schemas.py
   ```

   Use a default when old callers may omit the new field:

   ```python
   new_field: str = "default"
   ```

   But remember: a schema default only helps if service code actually uses that schema field when writing to DB.

4. Update service mappers and write paths.

   Check the service that owns the model:

   ```text
   backend/app/services/goal.py
   backend/app/services/learning_profile.py
   backend/app/services/roadmap.py
   backend/app/services/learning_memory.py
   backend/app/services/code_correction.py
   ```

   For new fields, update both directions:

   ```text
   schema/input -> DB row
   DB row -> schema/output
   ```

5. Update MCP/API contracts if agents or frontend need the field.

   Check:

   ```text
   backend/app/mcp/tools/goal.py
   backend/app/mcp/tools/learning_profile.py
   backend/app/mcp/tools/roadmap.py
   backend/app/mcp/tools/learning_memory.py
   backend/app/mcp/tools/code_correction.py
   ```

   If an agent should see the field, the output schema and service mapper must return it.

   If an agent should write the field, the MCP tool input and service validation must accept it.

6. Update tests and fixtures.

   Any test fixture that builds a Pydantic entity or DB row may need the new field, especially if the field is required.

   Add focused tests for:

   - Old input omits the new field and still works if backwards compatibility is intended.
   - New field is persisted.
   - New field is returned through the service/MCP response.
   - Invalid enum/status values fail early if strict values are required.

## Safe Patterns

### Adding A Nullable Or Defaulted Field

Good when old callers should keep working.

```text
DB column: nullable or has DB default
Schema field: has Pydantic default
Service create path: writes payload value or default
Service read path: returns DB value
```

### Adding A Required Field

Use a migration/backfill sequence.

```text
1. Add nullable column or DB default
2. Backfill existing rows
3. Update service/schema code
4. Enforce non-null if needed
```

### Enum-Like Status Fields

If the schema restricts values:

```python
Literal["ready", "generated", "revising", "completed", "revised"]
```

then the DB and services should only write those values. A raw DB `String` can store invalid values like `done` or `finished`, but those can later break Pydantic response validation.

Preferred pattern:

```text
Schema enum or Literal
Service-level validation before writes
Optional DB check constraint
Tests for invalid values
```

## Will Existing Tests Catch DB Model Problems?

Sometimes, but not always.

Existing tests are likely to catch the issue if they exercise the affected full path:

```text
service write
-> DB row
-> service read mapper
-> Pydantic schema
-> MCP/API response
```

Existing tests may miss the issue if:

- The new field is never read in tests.
- Tests use Pydantic objects directly and skip DB persistence.
- Tests use SQLite or mocks while production uses Postgres-specific behavior.
- The migration is not run in the test setup.
- The invalid value only appears in old production data.
- MCP serialization is not covered.

So after DB model changes, run affected service/MCP tests and add at least one test that goes through the real persistence and read path.

## Quick Rule

If the DB model changes, check these four layers before calling the change complete:

```text
DB model/migration
Pydantic schema
Service mapper/write logic
MCP/API contract
```

If the agent or frontend should see it, it must be present in the schema and returned by the service. If the agent or frontend should write it, it must be accepted by the MCP/API wrapper and validated before reaching the DB.
