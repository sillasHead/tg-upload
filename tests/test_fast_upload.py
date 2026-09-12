import math
import unittest

import fast_upload


class FastUploadTests(unittest.TestCase):
    def test_validate_workers(self):
        self.assertEqual(fast_upload.validate_workers(1), 1)
        self.assertEqual(fast_upload.validate_workers(4), 4)
        self.assertEqual(fast_upload.validate_workers(8), 8)
        with self.assertRaises(ValueError):
            fast_upload.validate_workers(0)
        with self.assertRaises(ValueError):
            fast_upload.validate_workers(9)

    def test_large_file_plan_uses_multiple_workers(self):
        size = 700 * 1024 * 1024
        part_size, part_count, workers = fast_upload.upload_plan(size, 4)
        self.assertGreater(part_size, 0)
        self.assertLessEqual(part_size, 512 * 1024)
        self.assertEqual(part_count, math.ceil(size / part_size))
        self.assertEqual(workers, 4)

    def test_tiny_file_does_not_create_idle_workers(self):
        part_size, part_count, workers = fast_upload.upload_plan(1024, 4)
        self.assertGreaterEqual(part_size, 1024)
        self.assertEqual(part_count, 1)
        self.assertEqual(workers, 1)

    def test_eta_format(self):
        self.assertEqual(fast_upload.ProgressReporter._format_eta(65), "01:05")
        self.assertEqual(fast_upload.ProgressReporter._format_eta(3661), "1:01:01")


if __name__ == "__main__":
    unittest.main()
