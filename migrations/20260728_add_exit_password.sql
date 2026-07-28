-- Optional parent-controlled exit password. Only a one-way password hash is
-- stored; the plain-text exit password must never be persisted.
SET @add_exit_password_hash = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'parents'
          AND column_name = 'exit_password_hash'
    ),
    'SELECT 1',
    'ALTER TABLE parents ADD COLUMN exit_password_hash VARCHAR(255) NULL'
);
PREPARE add_exit_password_hash_stmt FROM @add_exit_password_hash;
EXECUTE add_exit_password_hash_stmt;
DEALLOCATE PREPARE add_exit_password_hash_stmt;
