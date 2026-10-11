# The audit log is append-only in the database itself: UPDATE and DELETE raise, whoever issues
# them. TRUNCATE is still possible for the table owner (test teardown, a deliberate purge by a DBA).
from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION security_auditevent_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'security_auditevent is append-only (% refused)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER security_auditevent_no_update_or_delete
    BEFORE UPDATE OR DELETE ON security_auditevent
    FOR EACH ROW EXECUTE FUNCTION security_auditevent_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS security_auditevent_no_update_or_delete ON security_auditevent;
DROP FUNCTION IF EXISTS security_auditevent_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("security", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
