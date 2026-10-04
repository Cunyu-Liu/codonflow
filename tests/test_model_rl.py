import torch

from codonflow.models.edit_flow import (
    EditFlowConfig,
    EditFlowTransformer,
    edit_flow_loss,
)
from codonflow.data.dataset import collate_batch, fixed_length_noise_like
from codonflow.rl.rloo import (
    combined_reward,
    loo_advantage,
    rloo_loss,
    sequence_log_prob,
    RewardTracker,
)
from codonflow.eval.stop_checks import StopConditionChecker, StopThresholds


def _tiny_model():
    cfg = EditFlowConfig(d_model=32, n_layers=2, n_heads=4)
    return EditFlowTransformer(cfg)


def test_model_forward_shapes():
    model = _tiny_model()
    ids = torch.randint(0, 64, (2, 10))
    blank, tok = model(ids)
    assert blank.shape == (2, 10)
    assert tok.shape == (2, 10, 67)


def test_edit_flow_loss_finite():
    model = _tiny_model()
    ids = torch.randint(0, 64, (2, 10))
    x0 = fixed_length_noise_like(ids)
    blank, tok = model(x0)
    loss, b, t = edit_flow_loss(blank, tok, ids, edit_mask=(x0 != ids))
    assert torch.isfinite(loss)
    loss.backward()


def test_loo_advantage():
    r = torch.tensor([1.0, 2.0, 3.0, 4.0])
    a = loo_advantage(r)
    expected = torch.tensor([-2.0, -2.0 / 3, 2.0 / 3, 2.0])
    assert torch.allclose(a, expected, atol=1e-6)
    assert torch.allclose(a.mean(), torch.tensor(0.0), atol=1e-6)


def test_combined_reward():
    d = torch.tensor([1.0, 2.0])
    rv = torch.tensor([1.0, 0.0])
    c = combined_reward(d, rv, 1.0, 1.0, 0.5)
    assert torch.allclose(c, 0.5 * d + 0.5 * rv)


def test_rloo_loss_shape():
    log_pi = torch.tensor([0.1, 0.2, 0.3, 0.4])
    log_ref = torch.tensor([0.0, 0.0, 0.0, 0.0])
    rewards = torch.tensor([1.0, 2.0, 3.0, 4.0])
    loss = rloo_loss(log_pi, log_ref, rewards, beta=0.02)
    assert loss.dim() == 0


def test_sequence_log_prob():
    logits = torch.zeros(2, 4, 67)
    targets = torch.randint(0, 64, (2, 4))
    mask = torch.ones(2, 4)
    lp = sequence_log_prob(logits, targets, mask)
    assert lp.shape == (2,)
    assert torch.isfinite(lp).all()


def test_reward_tracker_plateau():
    tr = RewardTracker(patience=3, rel_tol=0.001)
    assert not tr.update(1.0)
    assert not tr.update(1.0)
    assert not tr.update(1.0)
    assert tr.update(1.0)
    assert tr.converged


def test_stop_conditions():
    chk = StopConditionChecker(StopThresholds())
    assert chk.check_feasible_rate(0.005)
    assert not chk.check_feasible_rate(0.5)
    assert chk.check_frame_break(0.06)
    assert chk.check_cost(6.0)
    assert chk.check_ned(0.5, 1.0)
    assert "cond1_feasible_rate" in chk.triggered
