"""Enemy motion prediction for aim lead."""

from combat import projectile_speed_for_variant
from ai import AIController
from ship import Ship, ShipVariant


def _warm_track(ctrl: AIController, shooter: Ship, target: Ship, steps: int = 4) -> None:
    for _ in range(steps):
        ctrl.update(shooter, [shooter, target], 0.05, [])


def test_accelerating_target_leads_further_ahead() -> None:
    shooter = Ship.create(ShipVariant.BALANCED, (0.0, 0.0), ship_id=1)
    target = Ship.create(ShipVariant.BALANCED, (400.0, 0.0), ship_id=2)
    target.velocity = (50.0, 0.0)
    ctrl = AIController.for_ship(shooter)
    ctrl.update(shooter, [shooter, target], 0.05, [])
    target.velocity = (130.0, 0.0)
    _warm_track(ctrl, shooter, target, steps=3)
    smart = ctrl.lead_target(shooter, target, None)
    bullet_time = 400.0 / projectile_speed_for_variant(shooter.variant)
    naive_x = 400.0 + 130.0 * bullet_time
    assert smart[0] > naive_x + 4.0


def test_turning_target_leads_off_velocity_line() -> None:
    shooter = Ship.create(ShipVariant.HEAVY, (400.0, 120.0), ship_id=1)
    target = Ship.create(ShipVariant.HEAVY, (400.0, 320.0), ship_id=2)
    target.velocity = (0.0, 70.0)
    target.angular_velocity = -1.6
    ctrl = AIController.for_ship(shooter)
    _warm_track(ctrl, shooter, target, steps=6)
    smart = ctrl.lead_target(shooter, target, None)
    bullet_time = 200.0 / projectile_speed_for_variant(shooter.variant)
    naive = (400.0, 320.0 + 70.0 * bullet_time)
    assert abs(smart[0] - naive[0]) > 6.0


def test_heavy_observer_gets_stronger_turn_lead() -> None:
    target = Ship.create(ShipVariant.BALANCED, (500.0, 300.0), ship_id=2)
    target.velocity = (90.0, 0.0)
    target.angular_velocity = 1.4
    heavy = Ship.create(ShipVariant.HEAVY, (200.0, 300.0), ship_id=1)
    light = Ship.create(ShipVariant.LIGHT, (200.0, 300.0), ship_id=3)
    heavy_ctrl = AIController.for_ship(heavy)
    light_ctrl = AIController.for_ship(light)
    _warm_track(heavy_ctrl, heavy, target, steps=5)
    _warm_track(light_ctrl, light, target, steps=5)
    heavy_lead = heavy_ctrl.lead_target(heavy, target, None)
    light_lead = light_ctrl.lead_target(light, target, None)
    assert heavy_lead[1] != light_lead[1]