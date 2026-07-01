"""运行 Recovery Ablation 实验"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.evaluation.recovery_experiment import RecoveryExperiment


def main() -> None:
    """运行实验"""
    workspace_dir = Path(__file__).parent.parent
    experiment = RecoveryExperiment(workspace_dir)
    report = experiment.run()
    print(experiment.format_report(report))


if __name__ == "__main__":
    main()
