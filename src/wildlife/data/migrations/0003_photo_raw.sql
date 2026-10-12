-- Migration 0003 (Phase 9): RAW originals, the camera, and where a photo's date came from.

-- A photo can carry its RAW original (e.g. a Pixel's .dng next to its .jpg). The JPEG is
-- what WildLife shows; the RAW file is kept beside it in the library, never changed, and
-- backed up like the photo itself. A RAW imported on its own is the photo's main file.
ALTER TABLE photo ADD COLUMN raw_sha256   TEXT    CHECK (raw_sha256 IS NULL OR length(raw_sha256) = 64);
ALTER TABLE photo ADD COLUMN raw_rel_path TEXT;
ALTER TABLE photo ADD COLUMN raw_name     TEXT;
ALTER TABLE photo ADD COLUMN raw_size     INTEGER CHECK (raw_size IS NULL OR raw_size > 0);
ALTER TABLE photo ADD COLUMN camera       TEXT;
-- 'exif' (the photo's own record), 'file_name' (e.g. PXL_20261011_083015123), 'manual'
ALTER TABLE photo ADD COLUMN taken_source TEXT CHECK (taken_source IN ('exif', 'file_name', 'manual'));

CREATE UNIQUE INDEX photo_raw_sha  ON photo (raw_sha256)   WHERE raw_sha256 IS NOT NULL;
CREATE UNIQUE INDEX photo_raw_path ON photo (raw_rel_path) WHERE raw_rel_path IS NOT NULL;
CREATE INDEX photo_deleted ON photo (deleted_at) WHERE deleted_at IS NOT NULL;

-- Photos imported before this phase got their date from EXIF (or have none)
UPDATE photo SET taken_source = 'exif' WHERE taken_at IS NOT NULL;
