-- Read-only diagnostic for the student business key used by Swing and Import Confirm.
-- This script does not modify data.
SELECT name, COALESCE(school_name, '') AS normalized_school_name, COUNT(*) AS duplicate_count
FROM student
GROUP BY name, COALESCE(school_name, '')
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, name, normalized_school_name;
