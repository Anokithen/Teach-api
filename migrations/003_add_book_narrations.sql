-- Run this once against an existing TeachAlike MySQL database before deploying
-- voice-cloned book narration. This project currently uses numbered SQL
-- migrations rather than an Alembic versions directory.
CREATE TABLE book_narrations (
  id INT NOT NULL AUTO_INCREMENT,
  book_id INT NOT NULL,
  voice_profile_id INT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'processing',
  narration_audio_url VARCHAR(500) NULL,
  cloudinary_public_id VARCHAR(255) NULL,
  error_message VARCHAR(500) NULL,
  created_at DATETIME NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_book_voice_narration UNIQUE (book_id, voice_profile_id),
  CONSTRAINT uq_book_narration_cloudinary_public_id UNIQUE (cloudinary_public_id),
  INDEX ix_book_narrations_book_voice (book_id, voice_profile_id),
  CONSTRAINT fk_book_narrations_book FOREIGN KEY (book_id) REFERENCES books(id),
  CONSTRAINT fk_book_narrations_voice_profile FOREIGN KEY (voice_profile_id) REFERENCES voice_profiles(id)
);
