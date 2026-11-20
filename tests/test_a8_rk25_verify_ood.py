#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO = Path('/home/codonflow-a8-rk')
sys.path.insert(0, str(REPO))
from scripts import a8_rk25_run_author_mechanism as production
from scripts import a8_rk25_verify_ood as independent

PROTOCOL = json.loads((REPO/'audits/20261121/RK25/a8_rk25_author_mechanism_protocol_v1.json').read_text())


def small_protocol():
    protocol = dict(PROTOCOL)
    protocol['statistics'] = dict(PROTOCOL['statistics'])
    protocol['statistics']['replicates'] = 20
    return protocol


def frames_for(protocol):
    rng = np.random.default_rng(29)
    frames = []
    for seed in protocol['seeds']:
        y = np.tile(np.arange(6),4).astype(float)
        frame = pd.DataFrame({
            'seed':[seed]*24, 'ood_assignment':['sequence_ood']*24,
            'expression_value':y, 'operational_protein_cluster':np.repeat(['a','b','c','d'],6),
        })
        for index,model in enumerate(production.MODELS):
            frame[model] = y + rng.normal(0,0.5+0.2*index,len(y))
        frames.append(frame)
    return frames


class RK25IndependentOODTests(unittest.TestCase):
    def test_01_bootstrap_cross_implementation(self):
        protocol = small_protocol()
        frames = frames_for(protocol)
        produced = production.hierarchical_bootstrap(frames,protocol)
        subset = frames[0]
        y = subset['expression_value'].to_numpy(float)
        clusters = subset['operational_protein_cluster'].to_numpy(str)
        predictions = {
            int(frame['seed'].iloc[0]):{model:frame[model].to_numpy(float) for model in production.MODELS}
            for frame in frames
        }
        replay = independent.independent_bootstrap(y,clusters,predictions,protocol)
        np.testing.assert_allclose(produced[0],replay[0],rtol=0,atol=1e-12)
        np.testing.assert_array_equal(produced[1],replay[1])
        np.testing.assert_array_equal(produced[2],replay[2])

    def test_02_summary_cross_implementation(self):
        protocol = small_protocol()
        frames = frames_for(protocol)
        metrics,_ = production.calculate_metrics(frames,protocol)
        points = production.point_comparisons(metrics,protocol)
        raw,_,_ = production.hierarchical_bootstrap(frames,protocol)
        produced = production.summarize_bootstrap(raw,points,protocol)
        replay = independent.independent_summary(raw,points,protocol)
        for left,right in zip(produced,replay):
            for key in ['point_delta_mean_per_seed','ci95_low','ci95_high','sign_pvalue','holm_pvalue']:
                self.assertAlmostEqual(float(left[key]),float(right[key]),places=10)
            for key in ['point_direction_pass','ci_direction_pass','direction_pass','endpoint_pass']:
                self.assertEqual(left[key],right[key])

    def test_03_spearman_ties(self):
        rng = np.random.default_rng(3)
        y = rng.integers(0,6,30)
        prediction = rng.integers(0,6,30)
        from scipy.stats import spearmanr
        self.assertAlmostEqual(independent.fast_spearman(y,prediction),spearmanr(y,prediction).statistic,places=12)

    def test_04_holm_known(self):
        observed = independent.holm_adjust([0.01,0.02,0.5])
        np.testing.assert_allclose(observed,[0.03,0.04,0.5])


if __name__=='__main__':
    unittest.main(verbosity=2)
