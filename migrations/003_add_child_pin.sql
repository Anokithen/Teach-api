-- Run this once against an existing TeachAlike MySQL database before deploying
-- the child-profile PIN feature. PINs are stored only as secure hashes.
ALTER TABLE children
  ADD COLUMN pin_hash VARCHAR(255) NULL AFTER reading_level;
