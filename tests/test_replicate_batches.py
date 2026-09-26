import unittest

from SigProfilerExtractor.subroutines import replicate_batches


class ReplicateBatchesTest(unittest.TestCase):
    def test_cpu_runs_one_task_per_replicate(self):
        for batch_size in (1, 2, 5):
            self.assertEqual(replicate_batches(10, batch_size, gpu=False), [1] * 10)

    def test_gpu_batches_cover_every_replicate(self):
        self.assertEqual(replicate_batches(10, 5, gpu=True), [5, 5])
        self.assertEqual(replicate_batches(10, 3, gpu=True), [3, 3, 3, 1])
        for batch_size in (1, 2, 3, 7, 10, 12):
            self.assertEqual(sum(replicate_batches(10, batch_size, gpu=True)), 10)


if __name__ == "__main__":
    unittest.main()
