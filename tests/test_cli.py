from ptp.cli import main


def test_dry_run_with_cpu(capsys):
    code = main(
        [
            "--dry-run",
            "-i",
            "inputs/nci195.pdf",
            "--tier",
            "flash",
            "--device",
            "cpu",
        ]
    )
    output = capsys.readouterr().out
    assert code == 0
    assert "resolved_device: cpu" in output
    assert "nci195.pdf" in output


def test_positional_input_supports_drag_and_drop(capsys):
    code = main(["--dry-run", "inputs/nci195.pdf", "--device", "cpu"])
    output = capsys.readouterr().out
    assert code == 0
    assert "nci195.pdf" in output
