-- Run this once against an existing TeachAlike MySQL database.
ALTER TABLE children
  ADD COLUMN gender VARCHAR(30) NOT NULL DEFAULT 'prefer_not_to_say' AFTER age;
