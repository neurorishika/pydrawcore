from pydrawcore.models import CalibrationModel, CalibrationSample, MotionConfig


def test_calibration_model_uses_piecewise_interpolation() -> None:
    model = CalibrationModel.fit(
        [
            CalibrationSample(parameter_value=100.0, measured_value=0.3),
            CalibrationSample(parameter_value=200.0, measured_value=0.8),
            CalibrationSample(parameter_value=300.0, measured_value=2.5),
        ]
    )

    assert model.fit_kind == "piecewise"
    assert model.resolve_parameter_for_measurement(1.65) == 250.0


def test_motion_config_round_trips_calibration_models(tmp_path) -> None:
    path = tmp_path / "motion.json"
    motion = MotionConfig(
        line_width_calibration=CalibrationModel.fit(
            [
                CalibrationSample(parameter_value=400.0, measured_value=0.9),
                CalibrationSample(parameter_value=800.0, measured_value=0.5),
            ]
        ),
        blot_delay_calibration=CalibrationModel.fit(
            [
                CalibrationSample(parameter_value=50.0, measured_value=0.5),
                CalibrationSample(parameter_value=150.0, measured_value=1.1),
            ]
        ),
    )

    motion.to_file(path)
    loaded = MotionConfig.from_file(path)

    assert loaded.feed_rate_for_line_width(0.7) == 600
    assert loaded.blot_delay_for_size(0.8) == 100
    assert loaded.line_width_calibration is not None
    assert loaded.line_width_calibration.samples[0].parameter_value == 400.0
