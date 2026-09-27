import unittest

from SigProfilerExtractor.subroutines import replicate_batches, split_generators


class ReplicateBatchesTest(unittest.TestCase):
    def test_cpu_runs_one_task_per_replicate(self):
        for batch_size in (1, 2, 5):
            self.assertEqual(replicate_batches(10, batch_size, gpu=False), [1] * 10)

    def test_gpu_batches_cover_every_replicate(self):
        self.assertEqual(replicate_batches(10, 5, gpu=True), [5, 5])
        self.assertEqual(replicate_batches(10, 3, gpu=True), [3, 3, 3, 1])
        for batch_size in (1, 2, 3, 7, 10, 12):
            self.assertEqual(sum(replicate_batches(10, batch_size, gpu=True)), 10)

    def test_every_replicate_keeps_its_own_generators(self):
        pairs = [("poisson%d" % k, "start%d" % k) for k in range(10)]
        for gpu, batch_size in ((False, 5), (True, 1), (True, 3), (True, 10)):
            groups = split_generators(pairs, replicate_batches(10, batch_size, gpu))
            self.assertEqual([p for group in groups for p in group], pairs)


if __name__ == "__main__":
    unittest.main()
