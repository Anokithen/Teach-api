-- Run this once against existing TeachAlike MySQL databases before using the
-- teacher child-management endpoints. Fresh databases get this column from
-- the SQLAlchemy model automatically.
ALTER TABLE children
  ADD COLUMN created_by_id INT NULL AFTER parent_id,
  ADD CONSTRAINT fk_children_created_by
    FOREIGN KEY (created_by_id) REFERENCES parents(id)
    ON DELETE SET NULL;
