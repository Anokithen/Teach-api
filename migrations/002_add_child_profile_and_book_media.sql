-- Run this once against an existing TeachAlike MySQL database before deploying
-- child profile PINs, gender, and catalog cover/video media.
ALTER TABLE children
  ADD COLUMN gender VARCHAR(30) NOT NULL DEFAULT 'prefer_not_to_say' AFTER age,
  ADD COLUMN child_pin_hash VARCHAR(255) NULL AFTER gender;

ALTER TABLE books
  ADD COLUMN cover_image_url VARCHAR(500) NULL AFTER content_url,
  ADD COLUMN video_url VARCHAR(500) NULL AFTER cover_image_url;
