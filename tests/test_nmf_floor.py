import unittest

import numpy as np
import torch

from SigProfilerExtractor import nmf_cpu, nmf_gpu


def sparse_matrix(pipeline_floor=False):
    # Raw counts with about two thirds zeros. pnmf() raises every value below 1e-4
    # to 1e-4 before NMF; pipeline_floor=True reproduces that.
    rng = np.random.default_rng(0)
    V = rng.poisson(0.4, size=(96, 400)).astype(np.float32)
    if pipeline_floor:
        V[V < 0.0001] = 0.0001
    return torch.from_numpy(V)


class NMFFloorTest(unittest.TestCase):
    backend = nmf_cpu

    def make_net(self, init_method, max_iterations, pipeline_floor=False):
        return self.backend.NMF(
            sparse_matrix(pipeline_floor),
            rank=11,
            generator=np.random.default_rng(1),
            init_method=init_method,
            min_iterations=max_iterations,
            max_iterations=max_iterations,
            test_conv=max_iterations,
        )

    def test_nndsvd_on_sparse_matrix_stays_finite(self):
        # Without the floor, on raw counts W @ H reaches exactly zero where V is zero
        # after about 200 iterations, and 0 / 0 turns every entry of W and H into NaN.
        net = self.make_net("nndsvd", max_iterations=2000)
        net.fit()
        self.assertTrue(torch.isfinite(net.W).all())
        self.assertTrue(torch.isfinite(net.H).all())
        self.assertTrue(np.isfinite(float(net._kl_loss)))

    def test_factors_never_reach_zero(self):
        net = self.make_net("nndsvd", max_iterations=500)
        net.fit()
        self.assertGreater(float(net.W.min()), 0.0)
        self.assertGreater(float(net.H.min()), 0.0)

    def test_nndsvd_zeros_are_not_locked_on_pipeline_input(self):
        # With V >= 1e-4 as in pnmf(), the old update produced no NaN, but the zeros
        # from the NNDSVD start (about half of W and H) stayed exactly zero forever.
        net = self.make_net("nndsvd", max_iterations=500, pipeline_floor=True)
        net.fit()
        self.assertEqual(int((net.W == 0).sum()), 0)
        self.assertEqual(int((net.H == 0).sum()), 0)

    def test_kl_loss_is_finite_when_data_has_zeros(self):
        # A NaN loss can never pass the convergence test, so every run would go to
        # max_iterations.
        net = self.make_net("random", max_iterations=1)
        self.assertTrue(np.isfinite(float(net._kl_loss)))


@unittest.skipUnless(torch.cuda.is_available(), "CUDA is not available")
class NMFFloorGPUTest(NMFFloorTest):
    backend = nmf_gpu


if __name__ == "__main__":
    unittest.main()
