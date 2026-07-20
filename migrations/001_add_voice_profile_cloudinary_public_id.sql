-- Run this once against an existing TeachAlike MySQL database before deploying
-- the private Cloudinary voice-recording feature.
ALTER TABLE voice_profiles
  ADD COLUMN cloudinary_public_id VARCHAR(255) NULL UNIQUE AFTER voice_sample_url;
