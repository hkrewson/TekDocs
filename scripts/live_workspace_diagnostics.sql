-- Read only the generated rehearsal database through its existing DB service.
-- Do not return event values, identifiers, recipients or transport configuration.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '3s';
SET LOCAL lock_timeout = '1s';
SELECT json_build_object(
    'schema_version', 1,
    'outbox', json_build_object(
        'pending', count(*) FILTER (WHERE state = 'pending'),
        'processing', count(*) FILTER (WHERE state = 'processing'),
        'delivered', count(*) FILTER (WHERE state = 'delivered'),
        'dead_letter', count(*) FILTER (WHERE state = 'dead_letter')
    ),
    'outbox_due', count(*) FILTER (WHERE state = 'pending' AND available_at <= now()),
    'outbox_unattempted', count(*) FILTER (WHERE attempts = 0),
    'outbox_delivery_errors', count(*) FILTER (WHERE last_error_code <> ''),
    'inbox', (
        SELECT json_build_object(
            'msp', count(*) FILTER (WHERE surface = 'msp'),
            'client_portal', count(*) FILTER (WHERE surface = 'client_portal')
        ) FROM core_inboxnotification
    )
) FROM core_outboxevent;
COMMIT;
