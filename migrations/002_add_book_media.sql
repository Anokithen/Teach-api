-- Run once against existing MySQL databases before deploying this update.
ALTER TABLE books ADD COLUMN cover_image_url VARCHAR(500) NULL AFTER content_url;
ALTER TABLE books ADD COLUMN video_url VARCHAR(500) NULL AFTER cover_image_url;
