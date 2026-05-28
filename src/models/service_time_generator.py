"""Service-time sampling for AGV unloading and operator processing."""

import numpy as np
from scipy.stats import rankdata, norm
from statsmodels.distributions.copula.api import GaussianCopula


class ServiceTimeGenerator:
    """Samples correlated AGV and operator service times by item count."""

    def __init__(self):
        self.data = {
            1: {"agv": np.array([2.24, 2.96, 2.45]), "op": np.array([10.33, 9.36, 9.18])},
            2: {"agv": np.array([5.32, 4.21, 4.68]), "op": np.array([19.15, 16.04, 19.48])},
            3: {"agv": np.array([7.37, 7.52, 8.28]), "op": np.array([21.10, 26.31, 28.39])},
            4: {"agv": np.array([10.98, 10.51, 10.53]), "op": np.array([34.25, 36.48, 25.71])},
        }

        agv_all = np.concatenate([self.data[i]["agv"] for i in self.data])
        op_all = np.concatenate([self.data[i]["op"] for i in self.data])

        u_agv = rankdata(agv_all) / (len(agv_all) + 1)
        u_op = rankdata(op_all) / (len(op_all) + 1)
        data_uniform = np.column_stack([u_agv, u_op])

        self.copula = GaussianCopula(k_dim=2)
        self.copula.fit_corr_param(data_uniform)

        self.items_keys = np.array([1, 2, 3, 4])
        agv_means = np.array([np.mean(self.data[i]["agv"]) for i in self.items_keys])
        op_means = np.array([np.mean(self.data[i]["op"]) for i in self.items_keys])

        self.agv_coef = np.polyfit(self.items_keys, agv_means, 1)
        self.op_coef = np.polyfit(self.items_keys, op_means, 1)

    def _extrapolate_mean(self, n_items, coef):
        return coef[0] * n_items + coef[1]

    def _get_stats(self, n_items):
        agv = self.data[n_items]["agv"]
        op = self.data[n_items]["op"]
        return {
            "agv_mu": np.mean(agv),
            "agv_sigma": np.std(agv, ddof=1),
            "op_mu": np.mean(op),
            "op_sigma": np.std(op, ddof=1),
        }

    def sample_service_time(self, n_items):
        """Return ``(agv_time, operator_time)`` for the given number of items."""
        if n_items <= 0:
            return 0.0, 0.0

        samples = np.atleast_2d(self.copula.rvs(1))
        u1, u2 = samples[0]

        if n_items in self.data:
            stats = self._get_stats(n_items)
            agv_mu = stats["agv_mu"]
            agv_sigma = stats["agv_sigma"]
            op_mu = stats["op_mu"]
            op_sigma = stats["op_sigma"]
        else:
            agv_mu = self._extrapolate_mean(n_items, self.agv_coef)
            op_mu = self._extrapolate_mean(n_items, self.op_coef)
            agv_sigma = 0.1 * agv_mu
            op_sigma = 0.1 * op_mu

        agv_time = norm.ppf(u1, loc=agv_mu, scale=agv_sigma)
        op_time = norm.ppf(u2, loc=op_mu, scale=op_sigma)

        return max(agv_time, 1.0), max(op_time, 5.0)
